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
import logging

from tripleo_common.utils import stack as stack_utils

LOG = logging.getLogger(__name__)


def generate_fencing_parameters(nodes_json, delay,
                                ipmi_level, ipmi_cipher, ipmi_lanplus):
    fence_params = {"EnableFencing": True, "FencingConfig": {}}
    devices = []

    for node in nodes_json:
        node_data = {}
        params = {}
        if "ports" in node:
            # Not all Ironic drivers present a MAC address, so we only
            # capture it if it's present
            mac_addr = node['ports'][0]['address'].lower()
            node_data["host_mac"] = mac_addr

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


def get_network_configs(heat, processed_data, container, role_name):
    # Default temporary value is used when no user input for any
    # interface routes for the role networks to find network config.
    role_networks = processed_data['template'].get('resources', {}).get(
        role_name + 'GroupVars', {}).get('properties', {}).get(
            'value', {}).get('role_networks', [])
    for nw in role_networks:
        rt = nw + 'InterfaceRoutes'
        if rt not in processed_data['environment']['parameter_defaults']:
            processed_data['environment']['parameter_defaults'][rt] = [[]]

    network_configs = stack_utils.preview_stack_and_network_configs(
        heat, processed_data, container, role_name)
    return network_configs
