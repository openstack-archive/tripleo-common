# Copyright 2016 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy
import json
import logging
import uuid

from heatclient import exc as heat_exc
from mistral_lib import actions
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common.actions import templates
from tripleo_common import constants
from tripleo_common import exception
from tripleo_common.utils import nodes
from tripleo_common.utils import parameters
from tripleo_common.utils import passwords as password_utils
from tripleo_common.utils import plan as plan_utils

LOG = logging.getLogger(__name__)


class GetParametersAction(templates.ProcessTemplatesAction):
    """Gets list of available heat parameters."""

    def run(self, context):

        cached = self.cache_get(context,
                                self.container,
                                "tripleo.parameters.get")

        if cached is not None:
            return cached

        processed_data = super(GetParametersAction, self).run(context)

        # If we receive a 'Result' instance it is because the parent action
        # had an error.
        if isinstance(processed_data, actions.Result):
            return processed_data

        processed_data['show_nested'] = True

        # respect previously user set param values
        swift = self.get_object_client(context)
        heat = self.get_orchestration_client(context)

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        params = env.get('parameter_defaults')

        fields = {
            'template': processed_data['template'],
            'files': processed_data['files'],
            'environment': processed_data['environment'],
            'show_nested': True
        }

        result = {
            'heat_resource_tree': heat.stacks.validate(**fields),
            'environment_parameters': params,
        }
        self.cache_set(context,
                       self.container,
                       "tripleo.parameters.get",
                       result)
        return result


class ResetParametersAction(base.TripleOAction):
    """Provides method to delete user set parameters."""

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME,
                 key=constants.DEFAULT_PLAN_ENV_KEY):
        super(ResetParametersAction, self).__init__()
        self.container = container
        self.key = key

    def run(self, context):
        swift = self.get_object_client(context)

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        try:
            plan_utils.update_in_env(swift, env, self.key,
                                     delete_key=True)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error updating environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        self.cache_delete(context,
                          self.container,
                          "tripleo.parameters.get")
        return env


class UpdateParametersAction(templates.ProcessTemplatesAction):
    """Updates plan environment with parameters."""

    def __init__(self, parameters,
                 container=constants.DEFAULT_CONTAINER_NAME,
                 key=constants.DEFAULT_PLAN_ENV_KEY):
        super(UpdateParametersAction, self).__init__()
        self.container = container
        self.parameters = parameters
        self.key = key

    def run(self, context):
        swift = self.get_object_client(context)
        heat = self.get_orchestration_client(context)

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        saved_env = copy.deepcopy(env)
        try:

            plan_utils.update_in_env(swift, env, self.key,
                                     self.parameters)

        except swiftexceptions.ClientException as err:
            err_msg = ("Error updating environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        processed_data = super(UpdateParametersAction, self).run(context)

        # If we receive a 'Result' instance it is because the parent action
        # had an error.
        if isinstance(processed_data, actions.Result):
            return processed_data

        processed_data['show_nested'] = True
        env = plan_utils.get_env(swift, self.container)

        params = env.get('parameter_defaults')
        fields = {
            'template': processed_data['template'],
            'files': processed_data['files'],
            'environment': processed_data['environment'],
            'show_nested': True
        }

        try:
            result = {
                'heat_resource_tree': heat.stacks.validate(**fields),
                'environment_parameters': params,
            }

            # Validation passes so the old cache gets replaced.
            self.cache_set(context,
                           self.container,
                           "tripleo.parameters.get",
                           result)

            if result['heat_resource_tree']:
                flattened = {'resources': {}, 'parameters': {}}
                _flat_it(flattened, 'Root',
                         result['heat_resource_tree'])
                result['heat_resource_tree'] = flattened

        except heat_exc.HTTPException as err:
            LOG.debug("Validation failed rebuilding saved env")

            # There has been an error validating we must reprocess the
            # templates with the saved working env
            plan_utils.put_env(swift, saved_env)
            env = saved_env
            processed_data = super(UpdateParametersAction, self).run(context)

            err_msg = ("Error validating environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        LOG.debug("Validation worked new env is saved")

        return result


class UpdateRoleParametersAction(UpdateParametersAction):
    """Updates role related parameters in plan environment ."""

    def __init__(self, role, container=constants.DEFAULT_CONTAINER_NAME):
        super(UpdateRoleParametersAction, self).__init__(parameters=None,
                                                         container=container)
        self.role = role

    def run(self, context):
        baremetal_client = self.get_baremetal_client(context)
        compute_client = self.get_compute_client(context)
        self.parameters = parameters.set_count_and_flavor_params(
            self.role, baremetal_client, compute_client)
        return super(UpdateRoleParametersAction, self).run(context)


class GeneratePasswordsAction(base.TripleOAction):
    """Generates passwords needed for Overcloud deployment

    This method generates passwords and ensures they are stored in the
    plan environment. This method respects previously generated passwords and
    adds new passwords as necessary.
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(GeneratePasswordsAction, self).__init__()
        self.container = container

    def run(self, context):
        heat = self.get_orchestration_client(context)
        swift = self.get_object_client(context)
        mistral = self.get_workflow_client(context)

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        try:
            stack_env = heat.stacks.environment(
                stack_id=self.container)

            # legacy heat resource names from overcloud.yaml
            # We don't modify these to avoid changing defaults
            for pw_res in constants.LEGACY_HEAT_PASSWORD_RESOURCE_NAMES:
                try:
                    res = heat.resources.get(self.container, pw_res)
                    param_defaults = stack_env.get('parameter_defaults', {})
                    param_defaults[pw_res] = res.attributes['value']
                except heat_exc.HTTPNotFound:
                    LOG.debug('Heat resouce not found: %s' % pw_res)
                    pass

        except heat_exc.HTTPNotFound:
            stack_env = None

        passwords = password_utils.generate_passwords(mistral, stack_env)

        # if passwords don't yet exist in plan environment
        if 'passwords' not in env:
            env['passwords'] = {}

        # ensure all generated passwords are present in plan env,
        # but respect any values previously generated and stored
        for name, password in passwords.items():
            if name not in env['passwords']:
                env['passwords'][name] = password

        try:
            plan_utils.put_env(swift, env)
        except swiftexceptions.ClientException as err:
            err_msg = "Error uploading to container: %s" % err
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        self.cache_delete(context,
                          self.container,
                          "tripleo.parameters.get")
        return env['passwords']


class GetPasswordsAction(base.TripleOAction):
    """Get passwords from the environment

    This method returns the list passwords which are used for the deployment.
    It will return a merged list of user provided passwords and generated
    passwords, giving priority to the user provided passwords.
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(GetPasswordsAction, self).__init__()
        self.container = container

    def run(self, context):
        swift = self.get_object_client(context)

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        parameter_defaults = env.get('parameter_defaults', {})
        passwords = env.get('passwords', {})

        return self._get_overriden_passwords(passwords, parameter_defaults)

    def _get_overriden_passwords(self, env_passwords, parameter_defaults):
        for name in constants.PASSWORD_PARAMETER_NAMES:
            if name in parameter_defaults:
                env_passwords[name] = parameter_defaults[name]
        return env_passwords


class GenerateFencingParametersAction(base.TripleOAction):
    """Generates fencing configuration for a deployment.

    :param nodes_json: list of nodes & attributes in json format
    :param os_auth: dictionary of OS client auth data (if using pxe_ssh)
    :param delay: time to wait before taking fencing action
    :param ipmi_level: IPMI user level to use
    :param ipmi_cipher: IPMI cipher suite to use
    :param ipmi_lanplus: whether to use IPMIv2.0
    """

    def __init__(self, nodes_json, os_auth, delay,
                 ipmi_level, ipmi_cipher, ipmi_lanplus):
        super(GenerateFencingParametersAction, self).__init__()
        self.nodes_json = nodes_json
        self.os_auth = os_auth
        self.delay = delay
        self.ipmi_level = ipmi_level
        self.ipmi_cipher = ipmi_cipher
        self.ipmi_lanplus = ipmi_lanplus

    def run(self, context):
        """Returns the parameters for fencing controller nodes"""
        hostmap = nodes.generate_hostmap(self.get_baremetal_client(context),
                                         self.get_compute_client(context))
        fence_params = {"EnableFencing": True, "FencingConfig": {}}
        devices = []

        for node in self.nodes_json:
            node_data = {}
            params = {}
            if "mac" in node:
                # Not all Ironic drivers present a MAC address, so we only
                # capture it if it's present
                mac_addr = node["mac"][0]
                node_data["host_mac"] = mac_addr

                # If the MAC isn't in the hostmap, this node hasn't been
                # provisioned, so no fencing parameters are necessary
                if hostmap and mac_addr not in hostmap:
                    continue

            # Build up fencing parameters based on which Ironic driver this
            # node is using
            if hostmap and node["pm_type"] == "pxe_ssh":
                # Ironic fencing driver
                node_data["agent"] = "fence_ironic"
                params["auth_url"] = self.os_auth["auth_url"]
                params["login"] = self.os_auth["login"]
                params["passwd"] = self.os_auth["passwd"]
                params["tenant_name"] = self.os_auth["tenant_name"]
                params["pcmk_host_map"] = "%(compute_name)s:%(bm_name)s" % (
                    {"compute_name": hostmap[mac_addr]["compute_name"],
                     "bm_name": hostmap[mac_addr]["baremetal_name"]})
                if self.delay:
                    params["delay"] = self.delay
            elif (node['pm_type'] == 'ipmi' or node["pm_type"].split('_')[1] in
                  ("ipmitool", "ilo", "drac")):
                # IPMI fencing driver
                node_data["agent"] = "fence_ipmilan"
                params["ipaddr"] = node["pm_addr"]
                params["passwd"] = node["pm_password"]
                params["login"] = node["pm_user"]
                if hostmap:
                    params["pcmk_host_list"] = \
                        hostmap[mac_addr]["compute_name"]
                if "pm_port" in node:
                    params["ipport"] = node["pm_port"]
                if self.ipmi_lanplus:
                    params["lanplus"] = self.ipmi_lanplus
                if self.delay:
                    params["delay"] = self.delay
                if self.ipmi_cipher:
                    params["cipher"] = self.ipmi_cipher
                if self.ipmi_level:
                    params["privlvl"] = self.ipmi_level
            else:
                error = ("Unable to generate fencing parameters for %s" %
                         node["pm_type"])
                raise ValueError(error)

            node_data["params"] = params
            devices.append(node_data)

        fence_params["FencingConfig"]["devices"] = devices
        return {"parameter_defaults": fence_params}


class GetFlattenedParametersAction(GetParametersAction):
    """Get the heat stack tree and parameters in flattened structure.

    This method validates the stack of the container and returns the
    parameters and the heat stack tree. The heat stack tree is flattened
    for easy consumption.
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(GetFlattenedParametersAction, self).__init__(container)

    def run(self, context):
        # process all plan files and create or update a stack
        processed_data = super(GetFlattenedParametersAction, self).run(context)

        # If we receive a 'Result' instance it is because the parent action
        # had an error.
        if isinstance(processed_data, actions.Result):
            return processed_data

        if processed_data['heat_resource_tree']:
            flattened = {'resources': {}, 'parameters': {}}
            _flat_it(flattened, 'Root',
                     processed_data['heat_resource_tree'])
            processed_data['heat_resource_tree'] = flattened

        return processed_data


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


class GetProfileOfFlavorAction(base.TripleOAction):
    """Gets the profile name for a given flavor name.

    Need flavor object to get profile name since get_keys method is
    not available for external access. so we have created an action
    to get profile name from flavor name.

    :param flavor_name: Flavor name

    :return: profile name
    """

    def __init__(self, flavor_name):
        super(GetProfileOfFlavorAction, self).__init__()
        self.flavor_name = flavor_name

    def run(self, context):
        compute_client = self.get_compute_client(context)
        try:
            return parameters.get_profile_of_flavor(self.flavor_name,
                                                    compute_client)
        except exception.DeriveParamsError as err:
            LOG.error('Derive Params Error: %s', err)
            return actions.Result(error=str(err))


class RotateFernetKeysAction(GetPasswordsAction):
    """Rotate fernet keys from the environment

    This method rotates the fernet keys that are saved in the environment, in
    the passwords parameter.
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(RotateFernetKeysAction, self).__init__()
        self.container = container

    def run(self, context):
        swift = self.get_object_client(context)

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        parameter_defaults = env.get('parameter_defaults', {})
        passwords = self._get_overriden_passwords(env.get('passwords', {}),
                                                  parameter_defaults)

        next_index = self.get_next_index(passwords['KeystoneFernetKeys'])
        keys_map = self.rotate_keys(passwords['KeystoneFernetKeys'],
                                    next_index)
        max_keys = self.get_max_keys_value(parameter_defaults)
        keys_map = self.purge_excess_keys(max_keys, keys_map)

        env['passwords']['KeystoneFernetKeys'] = keys_map

        try:
            plan_utils.put_env(swift, env)
        except swiftexceptions.ClientException as err:
            err_msg = "Error uploading to container: %s" % err
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        self.cache_delete(context,
                          self.container,
                          "tripleo.parameters.get")

        return keys_map

    @staticmethod
    def get_key_index_from_path(path):
        return int(path[path.rfind('/') + 1:])

    def get_next_index(self, keys_map):
        return self.get_key_index_from_path(
            max(keys_map, key=self.get_key_index_from_path)) + 1

    def get_key_path(self, index):
        return password_utils.KEYSTONE_FERNET_REPO + str(index)

    def rotate_keys(self, keys_map, next_index):
        next_index_path = self.get_key_path(next_index)
        zero_index_path = self.get_key_path(0)

        # promote staged key to be new primary
        keys_map[next_index_path] = keys_map[zero_index_path]
        # Set new staged key
        keys_map[zero_index_path] = {
            'content': password_utils.create_keystone_credential()}
        return keys_map

    def get_max_keys_value(self, parameter_defaults):
        # The number of max keys should always be positive. The minimum amount
        # of keys is 3.
        return max(parameter_defaults.get('KeystoneFernetMaxActiveKeys', 5), 3)

    def purge_excess_keys(self, max_keys, keys_map):
        current_repo_size = len(keys_map)
        if current_repo_size <= max_keys:
            return keys_map
        key_paths = sorted(keys_map.keys(), key=self.get_key_index_from_path)

        keys_to_be_purged = current_repo_size - max_keys

        for key_path in key_paths[1:keys_to_be_purged + 1]:
            del keys_map[key_path]
        return keys_map


class GetNetworkConfigAction(templates.ProcessTemplatesAction):
    """Gets network configuration details from available heat parameters."""

    def __init__(self, role_name, container=constants.DEFAULT_CONTAINER_NAME):
        super(GetNetworkConfigAction, self).__init__(container=container)
        self.role_name = role_name

    def run(self, context):

        processed_data = super(GetNetworkConfigAction, self).run(context)

        # If we receive a 'Result' instance it is because the parent action
        # had an error.
        if isinstance(processed_data, actions.Result):
            return processed_data

        # stacks.preview method raises validation message if stack is
        # already deployed. here renaming container to get preview data.
        container_temp = self.container + "-TEMP"
        fields = {
            'template': processed_data['template'],
            'files': processed_data['files'],
            'environment': processed_data['environment'],
            'stack_name': container_temp,
        }
        orc = self.get_orchestration_client(context)
        preview_data = orc.stacks.preview(**fields)
        try:
            result = self.get_network_config(preview_data, container_temp,
                                             self.role_name)
            return result
        except exception.DeriveParamsError as err:
            LOG.exception('Derive Params Error: %s' % err)
            return actions.Result(error=str(err))

    def get_network_config(self, preview_data, stack_name, role_name):
        result = None
        if preview_data:
            for res in preview_data.resources:
                net_script = self.process_preview_list(res,
                                                       stack_name,
                                                       role_name)
                if net_script:
                    ns_len = len(net_script)
                    start_index = (net_script.find(
                        "echo '{\"network_config\"", 0, ns_len) + 6)
                    end_index = net_script.find("'", start_index, ns_len)
                    if (end_index > start_index):
                        net_config = net_script[start_index:end_index]
                        if net_config:
                            result = json.loads(net_config)
                    break

        if not result:
            err_msg = ("Unable to determine network config for role '%s'."
                       % self.role_name)
            raise exception.DeriveParamsError(err_msg)

        return result

    def process_preview_list(self, res, stack_name, role_name):
        if type(res) == list:
            for item in res:
                out = self.process_preview_list(item, stack_name, role_name)
                if out:
                    return out
        elif type(res) == dict:
            res_stack_name = stack_name + '-' + role_name
            if res['resource_name'] == "OsNetConfigImpl" and \
                res['resource_identity'] and \
                res_stack_name in res['resource_identity']['stack_name']:
                return res['properties']['config']
        return None
