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

from mistral_lib import actions
import six

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common import exception
from tripleo_common.utils import parameters as parameter_utils
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
            return plan_utils.generate_passwords(
                swift, heat, mistral, container=self.container,
                rotate_passwords=self.rotate_passwords,
                rotate_pw_list=self.rotate_pw_list)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))


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
