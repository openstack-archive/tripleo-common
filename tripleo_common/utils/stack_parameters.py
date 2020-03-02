# Copyright 2016 Red Hat, Inc.
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
import copy
import logging

from heatclient import exc as heat_exc
from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
from tripleo_common.utils import parameters as param_utils
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import template as template_utils
from tripleo_common.utils import stack as stack_utils

LOG = logging.getLogger(__name__)


def get_flattened_parameters(swift, heat,
                             container=constants.DEFAULT_CONTAINER_NAME):
    cached = plan_utils.cache_get(
        swift, container, "tripleo.parameters.get")

    if cached is not None:
        return cached

    processed_data = template_utils.process_templates(
        swift, heat, container=container
    )

    # respect previously user set param values
    try:
        env = plan_utils.get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    processed_data = stack_utils.validate_stack_and_flatten_parameters(
        heat, processed_data, env)

    plan_utils.cache_set(swift, container,
                         "tripleo.parameters.get", processed_data)

    return processed_data


def update_parameters(swift, heat, parameters,
                      container=constants.DEFAULT_CONTAINER_NAME,
                      parameter_key=constants.DEFAULT_PLAN_ENV_KEY,
                      validate=True):
    try:
        env = plan_utils.get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    saved_env = copy.deepcopy(env)
    try:
        plan_utils.update_in_env(swift, env, parameter_key, parameters)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error updating environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    processed_data = template_utils.process_templates(
        swift, heat, container=container
    )

    env = plan_utils.get_env(swift, container)

    if not validate:
        return env

    try:
        processed_data = stack_utils.validate_stack_and_flatten_parameters(
            heat, processed_data, env)

        plan_utils.cache_set(swift, container,
                             "tripleo.parameters.get", processed_data)
    except heat_exc.HTTPException as err:
        LOG.debug("Validation failed rebuilding saved env")

        # There has been an error validating we must reprocess the
        # templates with the saved working env
        plan_utils.put_env(swift, saved_env)
        template_utils.process_custom_roles(swift, heat, container)

        err_msg = ("Error validating environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)
    return processed_data


def reset_parameters(swift, container=constants.DEFAULT_CONTAINER_NAME,
                     key=constants.DEFAULT_PLAN_ENV_KEY):
    try:
        env = plan_utils.get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    try:
        plan_utils.update_in_env(swift, env, key, None, delete_key=True)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error updating environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    plan_utils.cache_delete(swift, container, "tripleo.parameters.get")
    return env


def update_role_parameters(swift, heat, ironic, nova, role,
                           container=constants.DEFAULT_CONTAINER_NAME):
    parameters = param_utils.set_count_and_flavor_params(role, ironic, nova)
    return update_parameters(swift, heat, parameters, container)
