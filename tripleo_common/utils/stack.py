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
