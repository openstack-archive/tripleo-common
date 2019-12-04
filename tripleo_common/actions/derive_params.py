# Copyright 2017 Red Hat, Inc.
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
import math
import re

from mistral_lib import actions

from tripleo_common.actions import base
from tripleo_common import exception

LOG = logging.getLogger(__name__)


class GetDpdkNicsNumaInfoAction(base.TripleOAction):
    """Gets the DPDK NICs with MTU for NUMA nodes.

    Find the DPDK interface names from the network config and
    translate it to phsical interface names using the introspection
    data. And then find the NUMA node associated with the DPDK
    interface and the MTU value.

    :param network_configs: network config list
    :param inspect_data: introspection data
    :param mtu_default: mtu default value for NICs

    :return: DPDK NICs NUMA nodes info
    """

    def __init__(self, network_configs, inspect_data, mtu_default=1500):
        super(GetDpdkNicsNumaInfoAction, self).__init__()
        self.network_configs = network_configs
        self.inspect_data = inspect_data
        self.mtu_default = mtu_default

    # TODO(jpalanis): Expose this utility from os-net-config to sort
    # active nics
    def _natural_sort_key(self, s):
        nsre = re.compile('([0-9]+)')
        return [int(text) if text.isdigit() else text
                for text in re.split(nsre, s)]

    # TODO(jpalanis): Expose this utility from os-net-config to sort
    # active nics
    def _is_embedded_nic(self, nic):
        if (nic.startswith('em') or nic.startswith('eth') or
                nic.startswith('eno')):
            return True
        return False

    # TODO(jpalanis): Expose this utility from os-net-config to sort
    # active nics
    def _ordered_nics(self, interfaces):
        embedded_nics = []
        nics = []
        for iface in interfaces:
            nic = iface.get('name', '')
            if self._is_embedded_nic(nic):
                embedded_nics.append(nic)
            else:
                nics.append(nic)
        active_nics = (sorted(
            embedded_nics, key=self._natural_sort_key) +
            sorted(nics, key=self._natural_sort_key))
        return active_nics

    # Gets numa node id for physical NIC name
    def find_numa_node_id(self, numa_nics, nic_name):
        for nic_info in numa_nics:
            if nic_info.get('name', '') == nic_name:
                return nic_info.get('numa_node', None)
        return None

    # Get physical interface name for NIC name
    def get_physical_iface_name(self, ordered_nics, nic_name):
        if nic_name.startswith('nic'):
            # Nic numbering, find the actual interface name
            nic_number = int(nic_name.replace('nic', ''))
            if nic_number > 0:
                iface_name = ordered_nics[nic_number - 1]
                return iface_name
        return nic_name

    # Gets dpdk interfaces and mtu info for dpdk config
    # Default mtu(recommended 1500) is used if no MTU is set for DPDK NIC
    def get_dpdk_interfaces(self, dpdk_objs):
        mtu = self.mtu_default
        dpdk_ifaces = []
        for dpdk_obj in dpdk_objs:
            obj_type = dpdk_obj.get('type')
            mtu = dpdk_obj.get('mtu', self.mtu_default)
            if obj_type == 'ovs_dpdk_port':
                # Member interfaces of ovs_dpdk_port
                dpdk_ifaces.extend(dpdk_obj.get('members', []))
            elif obj_type == 'ovs_dpdk_bond':
                # ovs_dpdk_bond will have multiple ovs_dpdk_ports
                for bond_member in dpdk_obj.get('members', []):
                    if bond_member.get('type') == 'ovs_dpdk_port':
                        dpdk_ifaces.extend(bond_member.get('members', []))
        return (dpdk_ifaces, mtu)

    def run(self, context):
        interfaces = self.inspect_data.get('inventory',
                                           {}).get('interfaces', [])
        # Checks whether inventory interfaces information is not available
        # in introspection data.
        if not interfaces:
            msg = 'Introspection data does not have inventory.interfaces'
            return actions.Result(error=msg)

        numa_nics = self.inspect_data.get('numa_topology',
                                          {}).get('nics', [])
        # Checks whether numa topology nics information is not available
        # in introspection data.
        if not numa_nics:
            msg = 'Introspection data does not have numa_topology.nics'
            return actions.Result(error=msg)

        active_interfaces = [iface for iface in interfaces
                             if iface.get('has_carrier', False)]
        # Checks whether active interfaces are not available
        if not active_interfaces:
            msg = 'Unable to determine active interfaces (has_carrier)'
            return actions.Result(error=msg)

        dpdk_nics_numa_info = []
        ordered_nics = self._ordered_nics(active_interfaces)
        # Gets DPDK network config and parses to get DPDK NICs
        # with mtu and numa node id
        for config in self.network_configs:
            if config.get('type', '') == 'ovs_user_bridge':
                bridge_name = config.get('name', '')
                addresses = config.get('addresses', [])
                members = config.get('members', [])
                dpdk_ifaces, mtu = self.get_dpdk_interfaces(members)
                for dpdk_iface in dpdk_ifaces:
                    type = dpdk_iface.get('type', '')
                    if type == 'sriov_vf':
                        name = dpdk_iface.get('device', '')
                    else:
                        name = dpdk_iface.get('name', '')
                    phy_name = self.get_physical_iface_name(
                        ordered_nics, name)
                    node = self.find_numa_node_id(numa_nics, phy_name)
                    if node is None:
                        msg = ('Unable to determine NUMA node for '
                               'DPDK NIC: %s' % phy_name)
                        return actions.Result(error=msg)

                    dpdk_nic_info = {'name': phy_name,
                                     'numa_node': node,
                                     'mtu': mtu,
                                     'bridge_name': bridge_name,
                                     'addresses': addresses}
                    dpdk_nics_numa_info.append(dpdk_nic_info)
        return dpdk_nics_numa_info


class GetDpdkCoreListAction(base.TripleOAction):
    """Gets the DPDK PMD Core List.

    With input as the number of physical cores for each NUMA node,
    find the right logical CPUs to be allocated along with its
    siblings for the PMD core list.

    :param inspect_data: introspection data
    :param numa_nodes_cores_count: physical cores count for each NUMA

    :return: DPDK Core List
    """

    def __init__(self, inspect_data, numa_nodes_cores_count):
        super(GetDpdkCoreListAction, self).__init__()
        self.inspect_data = inspect_data
        self.numa_nodes_cores_count = numa_nodes_cores_count

    def run(self, context):
        dpdk_core_list = []
        numa_cpus_info = self.inspect_data.get('numa_topology',
                                               {}).get('cpus', [])

        # Checks whether numa topology cpus information is not available
        # in introspection data.
        if not numa_cpus_info:
            msg = 'Introspection data does not have numa_topology.cpus'
            return actions.Result(error=msg)

        # Checks whether CPU physical cores count for each NUMA nodes is
        # not available
        if not self.numa_nodes_cores_count:
            msg = ('CPU physical cores count for each NUMA nodes '
                   'is not available')
            return actions.Result(error=msg)

        numa_nodes_threads = {}
        # Creates list for all available threads in each NUMA node
        for cpu in numa_cpus_info:
            if not cpu['numa_node'] in numa_nodes_threads:
                numa_nodes_threads[cpu['numa_node']] = []
            numa_nodes_threads[cpu['numa_node']].extend(cpu['thread_siblings'])

        for node, node_cores_count in enumerate(self.numa_nodes_cores_count):
            # Gets least thread in NUMA node
            numa_node_min = min(numa_nodes_threads[node])
            cores_count = node_cores_count
            for cpu in numa_cpus_info:
                if cpu['numa_node'] == node:
                    # Adds threads from core which is not having least thread
                    if numa_node_min not in cpu['thread_siblings']:
                        dpdk_core_list.extend(cpu['thread_siblings'])
                        cores_count -= 1
                        if cores_count == 0:
                            break
        return ','.join([str(thread) for thread in dpdk_core_list])


class GetHostCpusListAction(base.TripleOAction):
    """Gets the Host CPUs List.

    CPU threads from first physical core is allocated for host processes
    on each NUMA nodes.

    :param inspect_data: introspection data

    :return: Host CPUs List
    """

    def __init__(self, inspect_data):
        super(GetHostCpusListAction, self).__init__()
        self.inspect_data = inspect_data

    def run(self, context):
        host_cpus_list = []
        numa_cpus_info = self.inspect_data.get('numa_topology',
                                               {}).get('cpus', [])

        # Checks whether numa topology cpus information is not available
        # in introspection data.
        if not numa_cpus_info:
            msg = 'Introspection data does not have numa_topology.cpus'
            return actions.Result(error=msg)

        numa_nodes_threads = {}
        # Creates a list for all available threads in each NUMA nodes
        for cpu in numa_cpus_info:
            if not cpu['numa_node'] in numa_nodes_threads:
                numa_nodes_threads[cpu['numa_node']] = []
            numa_nodes_threads[cpu['numa_node']].extend(
                cpu['thread_siblings'])

        for numa_node in sorted(numa_nodes_threads.keys()):
            node = int(numa_node)
            # Gets least thread in NUMA node
            numa_node_min = min(numa_nodes_threads[numa_node])
            for cpu in numa_cpus_info:
                if cpu['numa_node'] == node:
                    # Adds threads from core which is having least thread
                    if numa_node_min in cpu['thread_siblings']:
                        host_cpus_list.extend(cpu['thread_siblings'])
                        break

        return ','.join([str(thread) for thread in host_cpus_list])


class GetDpdkSocketMemoryAction(base.TripleOAction):
    """Gets the DPDK Socket Memory List.

    For NUMA node with DPDK nic, socket memory is calculated
    based on MTU, Overhead and Packet size in buffer.

    For NUMA node without DPDK nic, minimum socket memory is
    assigned (recommended 1GB)

    :param dpdk_nics_numa_info: DPDK nics numa info
    :param numa_nodes: list of numa nodes
    :param overhead: overhead value
    :param packet_size_in_buffer: packet size in buffer
    :param minimum_socket_memory: minimum socket memory

    :return: DPDK Socket Memory List
    """
    def __init__(self, dpdk_nics_numa_info, numa_nodes,
                 overhead, packet_size_in_buffer,
                 minimum_socket_memory=1024):
        super(GetDpdkSocketMemoryAction, self).__init__()
        self.dpdk_nics_numa_info = dpdk_nics_numa_info
        self.numa_nodes = numa_nodes
        self.overhead = overhead
        self.packet_size_in_buffer = packet_size_in_buffer
        self.minimum_socket_memory = minimum_socket_memory

    # Computes round off MTU value in bytes
    # example: MTU value 9000 into 9216 bytes
    def roundup_mtu_bytes(self, mtu):
        max_div_val = int(math.ceil(float(mtu) / float(1024)))
        return (max_div_val * 1024)

    # Calculates socket memory for a NUMA node
    def calculate_node_socket_memory(
        self, numa_node, dpdk_nics_numa_info, overhead,
            packet_size_in_buffer, minimum_socket_memory):
        distinct_mtu_per_node = []
        socket_memory = 0

        # For DPDK numa node
        for nics_info in dpdk_nics_numa_info:
            if (numa_node == nics_info['numa_node'] and
                    not nics_info['mtu'] in distinct_mtu_per_node):
                distinct_mtu_per_node.append(nics_info['mtu'])
                roundup_mtu = self.roundup_mtu_bytes(nics_info['mtu'])
                socket_memory += (((roundup_mtu + overhead) *
                                  packet_size_in_buffer) /
                                  (1024 * 1024))

        # For Non DPDK numa node
        if socket_memory == 0:
            socket_memory = minimum_socket_memory
        # For DPDK numa node
        else:
            socket_memory += 512

        socket_memory_in_gb = int(socket_memory / 1024)
        if socket_memory % 1024 > 0:
            socket_memory_in_gb += 1
        return (socket_memory_in_gb * 1024)

    def run(self, context):
        dpdk_socket_memory_list = []
        for node in self.numa_nodes:
            socket_mem = self.calculate_node_socket_memory(
                node, self.dpdk_nics_numa_info, self.overhead,
                self.packet_size_in_buffer,
                self.minimum_socket_memory)
            dpdk_socket_memory_list.append(socket_mem)

        return ','.join([str(sm) for sm in dpdk_socket_memory_list])


class ConvertNumberToRangeListAction(base.TripleOAction):
    """Converts number list into range list

    :param num_list: comma delimited number list as string

    :return: comma delimited range list as string
    """

    def __init__(self, num_list):
        super(ConvertNumberToRangeListAction, self).__init__()
        self.num_list = num_list

    # converts number list into range list.
    # here input parameter and return value as list
    # example: [12, 13, 14, 17] into ["12-14", "17"]
    def convert_number_to_range_list(self, num_list):
        num_list.sort()
        range_list = []
        range_min = num_list[0]
        for num in num_list:
            next_val = num + 1
            if next_val not in num_list:
                if range_min != num:
                    range_list.append(str(range_min) + '-' + str(num))
                else:
                    range_list.append(str(range_min))
                next_index = num_list.index(num) + 1
                if next_index < len(num_list):
                    range_min = num_list[next_index]

        # here, range_list is a list of strings
        return range_list

    def run(self, context):
        try:
            if not self.num_list:
                err_msg = ("Input param 'num_list' is blank.")
                raise exception.DeriveParamsError(err_msg)

            try:
                # splitting a string (comma delimited list) into
                # list of numbers
                # example: "12,13,14,17" string into [12,13,14,17]
                num_list = [int(num.strip(' '))
                            for num in self.num_list.split(",")]
            except ValueError as exc:
                err_msg = ("Invalid number in input param "
                           "'num_list': %s" % exc)
                raise exception.DeriveParamsError(err_msg)

            range_list = self.convert_number_to_range_list(num_list)
        except exception.DeriveParamsError as err:
            LOG.error('Derive Params Error: %s', err)
            return actions.Result(error=str(err))

        # converts into comma delimited range list as string
        return ','.join(range_list)


class ConvertRangeToNumberListAction(base.TripleOAction):
    """Converts range list to integer list

    :param range_list: comma delimited range list as string / list

    :return: comma delimited number list as string
    """

    def __init__(self, range_list):
        super(ConvertRangeToNumberListAction, self).__init__()
        self.range_list = range_list

    # converts range list into number list
    # here input parameter and return value as list
    # example: ["12-14", "^13", "17"] into [12, 14, 17]
    def convert_range_to_number_list(self, range_list):
        num_list = []
        exclude_num_list = []
        try:
            for val in range_list:
                val = val.strip(' ')
                if '^' in val:
                    exclude_num_list.append(int(val[1:]))
                elif '-' in val:
                    split_list = val.split("-")
                    range_min = int(split_list[0])
                    range_max = int(split_list[1])
                    num_list.extend(range(range_min, (range_max + 1)))
                else:
                    num_list.append(int(val))
        except ValueError as exc:
            err_msg = ("Invalid number in input param "
                       "'range_list': %s" % exc)
            raise exception.DeriveParamsError(err_msg)

        # here, num_list is a list of integers
        return [num for num in num_list if num not in exclude_num_list]

    def run(self, context):
        try:
            if not self.range_list:
                err_msg = ("Input param 'range_list' is blank.")
                raise exception.DeriveParamsError(err_msg)
            range_list = self.range_list
            # converts into python list if range_list is not list type
            if not isinstance(range_list, list):
                range_list = self.range_list.split(",")

            num_list = self.convert_range_to_number_list(range_list)
        except exception.DeriveParamsError as err:
            LOG.error('Derive Params Error: %s', err)
            return actions.Result(error=str(err))

        # converts into comma delimited number list as string
        return ','.join([str(num) for num in num_list])
