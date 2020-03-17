# Copyright 2017 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import time
import uuid

from heatclient.common import template_utils
from heatclient import exc as heat_exc
from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
from tripleo_common import update
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import template as templates

LOG = logging.getLogger(__name__)


def stack_update(swift, heat, timeout,
                 container=constants.DEFAULT_CONTAINER_NAME):
    # get the stack. Error if doesn't exist
    try:
        stack = heat.stacks.get(container)
    except heat_exc.HTTPNotFound:
        msg = "Error retrieving stack: %s" % container
        LOG.exception(msg)
        raise RuntimeError(msg)

    try:
        env = plan_utils.get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    update_env = {
        'parameter_defaults': {
            'DeployIdentifier': int(time.time()),
        },
    }

    noop_env = {
        'resource_registry': {
            'OS::TripleO::DeploymentSteps': 'OS::Heat::None',
        },
    }

    for output in stack.to_dict().get('outputs', {}):
        if output['output_key'] == 'RoleData':
            for role in output['output_value']:
                role_env = {
                    "OS::TripleO::Tasks::%sPreConfig" % role:
                    'OS::Heat::None',
                    "OS::TripleO::Tasks::%sPostConfig" % role:
                    'OS::Heat::None',
                }
                noop_env['resource_registry'].update(role_env)
    update_env.update(noop_env)
    template_utils.deep_update(env, update_env)
    try:
        plan_utils.put_env(swift, env)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error updating environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    # process all plan files and create or update a stack
    processed_data = templates.process_templates(
        swift, heat, container
    )
    stack_args = processed_data.copy()
    stack_args['timeout_mins'] = timeout

    LOG.info("Performing Heat stack update")
    LOG.info('updating stack: %s', stack.stack_name)
    return heat.stacks.update(stack.id, **stack_args)


def _process_params(flattened, params):
    for item in params:
        if item not in flattened['parameters']:
            param_obj = {}
            for key, value in params.get(item).items():
                camel_case_key = key[0].lower() + key[1:]
                param_obj[camel_case_key] = value
            param_obj['name'] = item
            flattened['parameters'][item] = param_obj
    return list(params)


def _flat_it(flattened, name, data):
    key = str(uuid.uuid4())
    value = {}
    value.update({
        'name': name,
        'id': key
    })
    if 'Type' in data:
        value['type'] = data['Type']
    if 'Description' in data:
        value['description'] = data['Description']
    if 'Parameters' in data:
        value['parameters'] = _process_params(flattened,
                                              data['Parameters'])
    if 'ParameterGroups' in data:
        value['parameter_groups'] = data['ParameterGroups']
    if 'NestedParameters' in data:
        nested = data['NestedParameters']
        nested_ids = []
        for nested_key in nested.keys():
            nested_data = _flat_it(flattened, nested_key,
                                   nested.get(nested_key))
            # nested_data will always have one key (and only one)
            nested_ids.append(list(nested_data)[0])

        value['resources'] = nested_ids

    flattened['resources'][key] = value
    return {key: value}


def validate_stack_and_flatten_parameters(heat, processed_data, env):
    params = env.get('parameter_defaults')
    fields = {
        'template': processed_data['template'],
        'files': processed_data['files'],
        'environment': processed_data['environment'],
        'show_nested': True
    }

    processed_data = {
        'heat_resource_tree': heat.stacks.validate(**fields),
        'environment_parameters': params,
    }

    if processed_data['heat_resource_tree']:
        flattened = {'resources': {}, 'parameters': {}}
        _flat_it(flattened, 'Root',
                 processed_data['heat_resource_tree'])
        processed_data['heat_resource_tree'] = flattened
    return processed_data


def deploy_stack(swift, heat, container, skip_deploy_identifier=False,
                 timeout_mins=240):
    try:
        stack = heat.stacks.get(container, resolve_outputs=False)
    except heat_exc.HTTPNotFound:
        stack = None

    stack_is_new = stack is None

    # update StackAction, DeployIdentifier and UpdateIdentifier

    parameters = dict()
    if not skip_deploy_identifier:
        parameters['DeployIdentifier'] = int(time.time())
    else:
        parameters['DeployIdentifier'] = ''
    parameters['StackAction'] = 'CREATE' if stack_is_new else 'UPDATE'

    try:
        env = plan_utils.get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    set_tls_parameters(parameters, env)
    try:
        plan_utils.update_in_env(swift, env, 'parameter_defaults',
                                 parameters)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error updating environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    if not stack_is_new:
        try:
            LOG.debug('Checking for compatible neutron mechanism drivers')
            msg = update.check_neutron_mechanism_drivers(env, stack,
                                                         swift,
                                                         container)
            if msg:
                raise RuntimeError(msg)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error getting template %s: %s" % (
                container, err))
            LOG.exception(err_msg)
            raise RuntimeError(err_msg)

    # process all plan files and create or update a stack
    processed_data = templates.process_templates(
        swift, heat, container=container,
        prune_services=True
    )
    stack_args = processed_data.copy()
    stack_args['timeout_mins'] = timeout_mins

    if stack_is_new:
        try:
            swift.copy_object(
                "%s-swift-rings" % container, "swift-rings.tar.gz",
                "%s-swift-rings/%s-%d" % (
                    container, "swift-rings.tar.gz", time.time()))
            swift.delete_object(
                "%s-swift-rings" % container, "swift-rings.tar.gz")
        except swiftexceptions.ClientException:
            pass
        LOG.info("Perfoming Heat stack create")
        try:
            return heat.stacks.create(**stack_args)
        except heat_exc.HTTPException as err:
            err_msg = "Error during stack creation: %s" % (err,)
            LOG.exception(err_msg)
            raise RuntimeError(err_msg)

    LOG.info("Performing Heat stack update")
    stack_args['existing'] = 'true'
    try:
        return heat.stacks.update(stack.id, **stack_args)
    except heat_exc.HTTPException as err:
        err_msg = "Error during stack update: %s" % (err,)
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)


def set_tls_parameters(parameters, env,
                       local_ca_path=constants.LOCAL_CACERT_PATH):

    def get_camap():
        return env['parameter_defaults'].get('CAMap', {})

    def get_updated_camap_entry(entry_name, cacert, orig_camap):
        ca_map_entry = {
            entry_name: {
                'content': cacert
            }
        }
        orig_camap.update(ca_map_entry)
        return orig_camap

    cacert_string = get_local_cacert(local_ca_path)
    if cacert_string:
        parameters['CAMap'] = get_updated_camap_entry(
            'undercloud-ca', cacert_string, get_camap())


def get_local_cacert(local_ca_path):
    # Since the undercloud has TLS by default, we'll add the undercloud's
    # CA to be trusted by the overcloud.
    try:
        with open(local_ca_path, 'rb') as ca_file:
            return ca_file.read().decode('utf-8')
    except IOError:
        # If the file wasn't found it means that the undercloud's TLS
        # was explicitly disabled or another CA is being used. So we'll
        # let the user handle this.
        return None
    except Exception:
        raise
