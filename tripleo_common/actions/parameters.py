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

import json
import logging

from heatclient import exc as heat_exc
from mistral_lib import actions
import six
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common import exception
from tripleo_common.utils import parameters as parameter_utils
from tripleo_common.utils import passwords as password_utils
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import stack_parameters as stack_param_utils
from tripleo_common.utils import template as template_utils

LOG = logging.getLogger(__name__)


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
            return stack_param_utils.reset_parameters(
                swift, self.container, self.key)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))


class UpdateParametersAction(base.TripleOAction):
    """Updates plan environment with parameters."""

    def __init__(self, parameters,
                 container=constants.DEFAULT_CONTAINER_NAME,
                 key=constants.DEFAULT_PLAN_ENV_KEY,
                 validate=True):
        super(UpdateParametersAction, self).__init__()
        self.container = container
        self.parameters = parameters
        self.key = key
        self.validate = validate

    def run(self, context):
        swift = self.get_object_client(context)
        heat = self.get_orchestration_client(context)

        try:
            return stack_param_utils.update_parameters(
                swift, heat, self.parameters,
                self.container, self.key,
                self.validate)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))


class UpdateRoleParametersAction(base.TripleOAction):
    """Updates role related parameters in plan environment ."""

    def __init__(self, role, container=constants.DEFAULT_CONTAINER_NAME):
        super(UpdateRoleParametersAction, self).__init__()
        self.role = role
        self.container = container

    def run(self, context):
        swift = self.get_object_client(context)
        heat = self.get_orchestration_client(context)
        ironic = self.get_baremetal_client(context)
        nova = self.get_compute_client(context)
        try:
            return stack_param_utils.update_role_parameters(
                swift, heat, ironic, nova, self.role, self.container)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))


class GeneratePasswordsAction(base.TripleOAction):
    """Generates passwords needed for Overcloud deployment

    This method generates passwords and ensures they are stored in the
    plan environment. By default, this method respects previously
    generated passwords and adds new passwords as necessary.

    If rotate_passwords is set to True, then passwords will be replaced as
    follows:
    - if password names are specified in the rotate_pw_list, then only those
      passwords will be replaced.
    - otherwise, all passwords not in the DO_NOT_ROTATE list (as they require
      special handling, like KEKs and Fernet keys) will be replaced.
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME,
                 rotate_passwords=False,
                 rotate_pw_list=[]):
        super(GeneratePasswordsAction, self).__init__()
        self.container = container
        self.rotate_passwords = rotate_passwords
        self.rotate_pw_list = rotate_pw_list

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

        passwords = password_utils.generate_passwords(
            mistralclient=mistral,
            stack_env=stack_env,
            rotate_passwords=self.rotate_passwords
        )

        # if passwords don't yet exist in plan environment
        if 'passwords' not in env:
            env['passwords'] = {}

        # NOTE(ansmith): if rabbit password previously generated and
        # stored, facilitate upgrade and use for oslo messaging in plan env
        if 'RabbitPassword' in env['passwords']:
            for i in ('RpcPassword', 'NotifyPassword'):
                if i not in env['passwords']:
                    env['passwords'][i] = env['passwords']['RabbitPassword']

        # ensure all generated passwords are present in plan env,
        # but respect any values previously generated and stored
        for name, password in passwords.items():
            if name not in env['passwords']:
                env['passwords'][name] = password

        if self.rotate_passwords:
            if len(self.rotate_pw_list) > 0:
                for name in self.rotate_pw_list:
                    env['passwords'][name] = passwords[name]
            else:
                for name, password in passwords.items():
                    if name not in constants.DO_NOT_ROTATE_LIST:
                        env['passwords'][name] = password

        try:
            plan_utils.put_env(swift, env)
        except swiftexceptions.ClientException as err:
            err_msg = "Error uploading to container: %s" % err
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        plan_utils.cache_delete(swift,
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
    :param delay: time to wait before taking fencing action
    :param ipmi_level: IPMI user level to use
    :param ipmi_cipher: IPMI cipher suite to use
    :param ipmi_lanplus: whether to use IPMIv2.0
    """

    def __init__(self, nodes_json, delay,
                 ipmi_level, ipmi_cipher, ipmi_lanplus):
        super(GenerateFencingParametersAction, self).__init__()
        self.nodes_json = nodes_json
        self.delay = delay
        self.ipmi_level = ipmi_level
        self.ipmi_cipher = ipmi_cipher
        self.ipmi_lanplus = ipmi_lanplus

    def run(self, context):
        """Returns the parameters for fencing controller nodes"""
        try:
            return stack_param_utils.generate_fencing_parameters(
                self.get_baremetal_client(context),
                self.get_compute_client(context),
                self.nodes_json,
                self.delay, self.ipmi_level,
                self.ipmi_cipher, self.ipmi_lanplus)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))


class GetFlattenedParametersAction(base.TripleOAction):
    """Get the heat stack tree and parameters in flattened structure.

    This method validates the stack of the container and returns the
    parameters and the heat stack tree. The heat stack tree is flattened
    for easy consumption.
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(GetFlattenedParametersAction, self).__init__()
        self.container = container

    def run(self, context):
        heat = self.get_orchestration_client(context)
        swift = self.get_object_client(context)
        try:
            return stack_param_utils.get_flattened_parameters(
                swift, heat, self.container)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))


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
            return parameter_utils.get_profile_of_flavor(self.flavor_name,
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

        plan_utils.cache_delete(swift,
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


class GetNetworkConfigAction(base.TripleOAction):
    """Gets network configuration details from available heat parameters."""

    def __init__(self, role_name, container=constants.DEFAULT_CONTAINER_NAME):
        super(GetNetworkConfigAction, self).__init__()
        self.container = container
        self.role_name = role_name

    def run(self, context):
        swift = self.get_object_client(context)
        heat = self.get_orchestration_client(context)

        processed_data = template_utils.process_templates(
            swift, heat, container=self.container
        )

        # Default temporary value is used when no user input for any
        # interface routes for the role networks to find network config.
        role_networks = processed_data['template'].get('resources', {}).get(
            self.role_name + 'GroupVars', {}).get('properties', {}).get(
                'value', {}).get('role_networks', [])
        for nw in role_networks:
            rt = nw + 'InterfaceRoutes'
            if rt not in processed_data['environment']['parameter_defaults']:
                processed_data['environment']['parameter_defaults'][rt] = [[]]

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
                    # In file network/scripts/run-os-net-config.sh
                    end_str = "' > /etc/os-net-config/config.json"
                    end_index = net_script.find(end_str, start_index, ns_len)
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
