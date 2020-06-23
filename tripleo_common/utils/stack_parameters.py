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
from tripleo_common.utils import nodes
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


def generate_fencing_parameters(ironic, compute, nodes_json, delay,
                                ipmi_level, ipmi_cipher, ipmi_lanplus):
    hostmap = nodes.generate_hostmap(ironic, compute)
    fence_params = {"EnableFencing": True, "FencingConfig": {}}
    devices = []
    nodes_json = nodes.convert_nodes_json_mac_to_ports(nodes_json)

    for node in nodes_json:
        node_data = {}
        params = {}
        if "ports" in node:
            # Not all Ironic drivers present a MAC address, so we only
            # capture it if it's present
            mac_addr = node['ports'][0]['address'].lower()
            node_data["host_mac"] = mac_addr

            # If the MAC isn't in the hostmap, this node hasn't been
            # provisioned, so no fencing parameters are necessary
            if hostmap and mac_addr not in hostmap:
                continue

        # Build up fencing parameters based on which Ironic driver this
        # node is using
        try:
            # Deprecated classic drivers (pxe_ipmitool, etc)
            driver_proto = node['pm_type'].split('_')[1]
        except IndexError:
            # New-style hardware types (ipmi, etc)
            driver_proto = node['pm_type']

        if driver_proto in {'ipmi', 'ipmitool', 'drac', 'idrac', 'ilo',
                            'redfish'}:
            if driver_proto == "redfish":
                node_data["agent"] = "fence_redfish"
                params["systems_uri"] = node["pm_system_id"]
            else:
                node_data["agent"] = "fence_ipmilan"
                if ipmi_lanplus:
                    params["lanplus"] = ipmi_lanplus
            params["ipaddr"] = node["pm_addr"]
            params["passwd"] = node["pm_password"]
            params["login"] = node["pm_user"]
            if hostmap:
                params["pcmk_host_list"] = \
                    hostmap[mac_addr]["compute_name"]
            if "pm_port" in node:
                params["ipport"] = node["pm_port"]
            if "redfish_verify_ca" in node:
                if node["redfish_verify_ca"] == "false":
                    params["ssl_insecure"] = "true"
                else:
                    params["ssl_insecure"] = "false"
            if delay:
                params["delay"] = delay
            if ipmi_cipher:
                params["cipher"] = ipmi_cipher
            if ipmi_level:
                params["privlvl"] = ipmi_level
        elif driver_proto in {'staging-ovirt'}:
            # fence_rhevm
            node_data["agent"] = "fence_rhevm"
            params["ipaddr"] = node["pm_addr"]
            params["passwd"] = node["pm_password"]
            params["login"] = node["pm_user"]
            params["port"] = node["pm_vm_name"]
            params["ssl"] = 1
            params["ssl_insecure"] = 1
            if hostmap:
                params["pcmk_host_list"] = \
                    hostmap[mac_addr]["compute_name"]
            if delay:
                params["delay"] = delay
        else:
            error = ("Unable to generate fencing parameters for %s" %
                     node["pm_type"])
            raise ValueError(error)

        node_data["params"] = params
        devices.append(node_data)

    fence_params["FencingConfig"]["devices"] = devices
    return {"parameter_defaults": fence_params}
