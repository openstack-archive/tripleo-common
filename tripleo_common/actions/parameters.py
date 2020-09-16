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

import logging

from mistral_lib import actions
import six

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common import exception
from tripleo_common.utils import parameters as parameter_utils
from tripleo_common.utils import stack_parameters as stack_param_utils

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
        try:
            return stack_param_utils.get_network_configs(
                self.get_baremetal_client(context),
                self.get_compute_client(context),
                self.container, self.role_name)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))
