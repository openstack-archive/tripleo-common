#!/usr/bin/env python

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

from collections import OrderedDict
import copy
import logging
import os
import sys
import tempfile
import yaml

from heatclient.exc import HTTPNotFound
import keystoneauth1
import openstack

from tripleo_common import exception
from tripleo_common import constants
from tripleo_common import inventories

HOST_NETWORK = 'ctlplane'
DEFAULT_DOMAIN = 'localdomain.'

UNDERCLOUD_CONNECTION_SSH = 'ssh'

UNDERCLOUD_CONNECTION_LOCAL = 'local'

logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


class TemplateDumper(yaml.SafeDumper):
    def represent_ordered_dict(self, data):
        return self.represent_dict(data.items())


TemplateDumper.add_representer(OrderedDict,
                               TemplateDumper.represent_ordered_dict)


class StackOutputs(object):
    """Item getter for stack outputs.

    It takes a long time to resolve stack outputs.  This class ensures that
    we only have to do it once and then reuse the results from that call in
    subsequent lookups.  It also lazy loads the outputs so we don't spend time
    on unnecessary Heat calls.
    """

    def __init__(self, stack):
        self.outputs = {}
        self.stack = stack

    def _load_outputs(self):
        """Load outputs from the stack if necessary

        Retrieves the stack outputs if that has not already happened.  If it
        has then this is a noop.
        """
        if not self.outputs:
            self.outputs = {i['output_key']: i['output_value']
                            for i in self.stack.outputs
                            }

    def __getitem__(self, key):
        self._load_outputs()
        return self.outputs[key]

    def __iter__(self):
        self._load_outputs()
        return iter(self.outputs.keys())

    def get(self, key, default=None):
        try:
            self.__getitem__(key)
        except KeyError:
            pass
        return self.outputs.get(key, default)


class NeutronData(object):
    """Neutron inventory data.

    A data object with for inventory generation enriched neutron data.
    """
    def __init__(self, networks, subnets, ports, host_network=None):
        self.networks = networks
        self.subnets = subnets
        self.ports = ports
        self.host_network = host_network or HOST_NETWORK
        self.networks_by_id = self._networks_by_id()
        self.subnets_by_id = self._subnets_by_id()
        self.ports_by_role_and_host = self._ports_by_role_and_host()

    def _tags_to_dict(self, tags):
        tag_dict = dict()
        for tag in tags:
            if not tag.startswith('tripleo_'):
                continue
            try:
                key, value = tag.rsplit('=')
            except ValueError:
                continue

            # Make booleans type bool
            value = True if value in {'True', 'true', True} else value
            value = False if value in {'False', 'false', False} else value

            # Convert network index value to integer
            if key == 'tripleo_net_idx':
                value = int(value)

            tag_dict.update({key: value})

        return tag_dict

    def _ports_by_role_and_host(self):
        mandatory_tags = {'tripleo_role'}

        ports_by_role_and_host = {}
        for port in self.ports:
            # Ignore ports in networks we ignore, i.e the OVN Bridge MAC net
            if port.network_id not in self.networks_by_id:
                continue

            tags = self._tags_to_dict(port.tags)

            # In case of missing required tags, raise an error.
            # neutron is useless as a inventory source in this case.
            if not mandatory_tags.issubset(tags):
                raise exception.MissingMandatoryNeutronResourceTag()

            hostname = port.dns_name
            # Strip the final fqdn dot of the hostname
            # See: https://bugs.launchpad.net/tripleo/+bug/1928869
            if hostname.endswith('.'):
                hostname = hostname[:-1]

            network_id = port.network_id
            network = self.networks_by_id[network_id]
            fixed_ips = port.fixed_ips[0]
            subnet_id = fixed_ips.get('subnet_id')
            subnet = self.subnets_by_id[subnet_id]

            # "TripleO" cidr is the number of bits in the network mask
            cidr = subnet['cidr'].split('/')[1]
            dns_domain = network['dns_domain']
            # Strip the final fqdn dot of the dnsname
            # See: https://bugs.launchpad.net/tripleo/+bug/1928869
            if dns_domain.endswith('.'):
                dns_domain = dns_domain[:-1]

            dns_nameservers = subnet['dns_nameservers']
            mtu = network['mtu']
            net_name = network['name']
            ip_address = fixed_ips.get('ip_address')
            gateway_ip = subnet['gateway_ip']
            # Need deepcopy here so that adding default entry does not end
            # up in the subnet object and leak to other nodes with a different
            # default route network.
            host_routes = copy.deepcopy(subnet['host_routes'])
            # If this is the default route network, add a default route using
            # gateway_ip to the host_routes unless it's already present
            if tags.get('tripleo_default_route'):
                host_routes.append({'default': True, 'nexthop': gateway_ip})

            vlan_id = subnet['tags'].get('tripleo_vlan_id',
                                         constants.DEFAULT_VLAN_ID)
            role_name = tags['tripleo_role']

            role = ports_by_role_and_host.setdefault(role_name, {})
            host = role.setdefault(hostname, [])
            host.append(
                {'name': port.name,
                 'hostname': hostname,
                 'dns_domain': dns_domain,
                 'network_id': network_id,
                 'network_name': net_name,
                 'fixed_ips': port.fixed_ips,
                 'subnet_id': subnet_id,
                 'ip_address': ip_address,
                 'mtu': mtu,
                 'cidr': cidr,
                 'gateway_ip': gateway_ip,
                 'dns_nameservers': dns_nameservers,
                 'host_routes': host_routes,
                 'vlan_id': vlan_id,
                 'tags': tags}
            )

        return ports_by_role_and_host

    def _networks_by_id(self):
        mandatory_tags = {'tripleo_network_name'}
        networks_by_id = {}
        for net in self.networks:
            # Don't include the OVN Bridge MAC address net
            if net.name == constants.OVN_MAC_ADDR_NET_NAME:
                continue

            tags = self._tags_to_dict(net.tags)
            # In case of missing required tags, raise an error.
            # neutron is useless as a inventory source in this case.
            if (net.name != self.host_network and
                    not mandatory_tags.issubset(tags)):
                raise exception.MissingMandatoryNeutronResourceTag()

            if net.name != self.host_network:
                name_upper = tags['tripleo_network_name']
            else:
                name_upper = self.host_network
            networks_by_id.update(
                {net.id: {'name': net.name,
                          'name_upper': name_upper,
                          'subnet_ids': net.subnet_ids,
                          'mtu': net.mtu,
                          'dns_domain': net.dns_domain,
                          'tags': tags}
                 }
            )

        return networks_by_id

    def _subnets_by_id(self):
        subnets_by_id = {}
        for subnet in self.subnets:
            subnets_by_id.update(
                {subnet.id: {'name': subnet.name,
                             'network_id': subnet.network_id,
                             'ip_version': subnet.ip_version,
                             'gateway_ip': subnet.gateway_ip,
                             'cidr': subnet.cidr,
                             'host_routes': subnet.host_routes,
                             'dns_nameservers': subnet.dns_nameservers,
                             'tags': self._tags_to_dict(subnet.tags)}
                 }
            )

        return subnets_by_id


class TripleoInventory(object):
    def __init__(self, cloud_name=None, session=None,
                 hclient=None, plan_name=None,
                 auth_url=None, project_name=None, cacert=None,
                 username=None, ansible_ssh_user=None,
                 host_network=None, ansible_python_interpreter=None,
                 undercloud_connection=UNDERCLOUD_CONNECTION_LOCAL,
                 undercloud_key_file=None, serial=1, work_dir=None):

        self.connection = None
        if cloud_name:
            self.connection = openstack.connect(cloud=cloud_name)
        elif session:
            self.connection = openstack.connection.Connection(session=session)

        self.hclient = hclient
        self.host_network = host_network or HOST_NETWORK
        self.ansible_ssh_user = ansible_ssh_user
        self.undercloud_key_file = undercloud_key_file
        self.plan_name = self.plan_group_name = plan_name
        self.ansible_python_interpreter = ansible_python_interpreter
        self.hostvars = {}
        self.undercloud_connection = undercloud_connection
        self.serial = serial
        self.work_dir = work_dir

    @staticmethod
    def get_roles_by_service(enabled_services):
        # Flatten the lists of services for each role into a set
        services = set(
            [item for role_services in enabled_services.values()
             for item in role_services])

        roles_by_services = {}
        for service in services:
            roles_by_services[service] = []
            for role, val in enabled_services.items():
                if service in val:
                    roles_by_services[service].append(role)
            roles_by_services[service] = sorted(roles_by_services[service])
        return roles_by_services

    def get_overcloud_environment(self):
        try:
            environment = self.hclient.stacks.environment(self.plan_name)
            return environment
        except (HTTPNotFound,
                keystoneauth1.exceptions.catalog.EndpointNotFound):
            return {}

    UNDERCLOUD_SERVICES = ['tripleo_ironic_conductor']

    def get_undercloud_service_list(self):
        """Return list of undercloud services - currently static

        Replace this when we have a better way - e.g. heat deploys undercloud
        """
        return self.UNDERCLOUD_SERVICES

    def _hosts(self, alist, dynamic=True):
        """Static yaml inventories reqire a different hosts format?!"""
        if not dynamic:
            return {x: {} for x in alist}
        return alist

    def _get_stack(self):
        if self.plan_name is None:
            return None
        try:
            stack = self.hclient.stacks.get(self.plan_name)
        except (HTTPNotFound,
                keystoneauth1.exceptions.catalog.EndpointNotFound):
            stack = None

        return stack

    def _inventory_from_heat_outputs(self, ret, children, dynamic):
        if not self.stack:
            return

        vip_map = self.stack_outputs.get('VipMap', {})
        role_net_ip_map = self.stack_outputs.get('RoleNetIpMap', {})
        role_node_id_map = self.stack_outputs.get('ServerIdData', {})
        networks = set()
        role_net_hostname_map = self.stack_outputs.get(
            'RoleNetHostnameMap', {})
        for role_name, hostnames in role_net_hostname_map.items():
            if not hostnames:
                continue

            net_ip_map = role_net_ip_map[role_name]
            try:
                ips = net_ip_map[self.host_network]
            except KeyError:
                LOG.warning(
                    "Network key %s not found, check role data for %s",
                    self.host_network,
                    role_name
                )
                continue

            if not ips:
                raise Exception("No IPs found for %s role on %s network" %
                                (role_name, self.host_network))

            net_hostname_map = role_net_hostname_map[role_name]
            bootstrap_server_id = role_node_id_map.get('bootstrap_server_id')
            node_id_map = role_node_id_map.get('server_ids')
            if node_id_map:
                srv_id_map = node_id_map.get(role_name)

            role_networks = sorted([str(net) for net in net_ip_map])
            networks.update(role_networks)

            # Undercloud role in the stack should overwrite, not append.
            # See bug: https://bugs.launchpad.net/tripleo/+bug/1913551
            if role_name == 'Undercloud':
                role = ret[role_name] = {}
            else:
                role = ret.setdefault(role_name, {})

            hosts = role.setdefault('hosts', {})
            role_vars = role.setdefault('vars', {})

            role_vars.setdefault('ansible_ssh_user', self.ansible_ssh_user)
            role_vars.setdefault('bootstrap_server_id', bootstrap_server_id)
            role_vars.setdefault('tripleo_role_name', role_name)
            role_vars.setdefault('tripleo_role_networks', role_networks)
            role_vars.setdefault('serial', self.serial)

            if self.ansible_python_interpreter:
                role_vars.setdefault('ansible_python_interpreter',
                                     self.ansible_python_interpreter)

            names = hostnames.get(self.host_network) or []
            shortnames = [n.split(".%s." % self.host_network)[0].lower()
                          for n in names]

            for idx, name in enumerate(shortnames):
                host = hosts.setdefault(name, {})
                host.setdefault('ansible_host', ips[idx])

                if srv_id_map:
                    host.setdefault('deploy_server_id', srv_id_map[idx])

                # Add variable for IP on each network
                for net in net_ip_map:
                    host.setdefault('{}_ip'.format(net), net_ip_map[net][idx])

                # Add variables for hostname on each network
                for net in net_hostname_map:
                    host.setdefault(
                        '{}_hostname'.format(net), net_hostname_map[net][idx])

            children.add(role_name)

            self.hostvars.update(hosts)

            if dynamic:
                hosts_format = [h for h in hosts.keys()]
                hosts_format.sort()
                ret[role_name]['hosts'] = hosts_format

        if children:
            plan_group = ret.setdefault(self.plan_name, {})
            overcloud_vars = plan_group.setdefault('vars', {})

            for vip_name, vip in vip_map.items():
                if vip and (vip_name in networks or vip_name == 'redis'):
                    overcloud_vars.setdefault('{}_vip'.format(vip_name), vip)

            overcloud_vars.setdefault(
                'container_cli', self.get_overcloud_environment().get(
                    'parameter_defaults', {}).get('ContainerCli'))

            plan_group.setdefault(
                'children', self._hosts(sorted(children), dynamic)
            )

            ret.setdefault(
                'allovercloud', {
                    'children': self._hosts([self.plan_name], dynamic)
                }
                )

        # Associate services with roles
        roles_by_service = self.get_roles_by_service(
            self.stack_outputs.get('EnabledServices', {}))

        # tripleo-groups map to ceph-ansible groups as follows
        ceph_group_map = {
            'ceph_mon': 'mons',
            'ceph_osd': 'osds',
            'ceph_mgr': 'mgrs',
            'ceph_rgw': 'rgws',
            'ceph_mds': 'mdss',
            'ceph_nfs': 'nfss',
            'ceph_client': 'clients',
            'ceph_rbdmirror': 'rbdmirrors',
            'ceph_grafana': 'grafana-server'
        }
        # add a ceph-ansible compatible group to the inventory
        # which has the same roles. E.g. if the inventory has
        # a group 'ceph_mon' which has childen and vars, then
        # the inventory will now also have a group 'mons' with
        # the same children and vars.
        for service, roles in roles_by_service.copy().items():
            if service in ceph_group_map.keys():
                roles_by_service[ceph_group_map[service]] = roles

        for service, roles in roles_by_service.items():
            service_children = [role for role in roles
                                if ret.get(role) is not None]
            if service_children:
                svc_host = ret.setdefault(service.lower(), {})
                svc_host_vars = svc_host.setdefault('vars', {})
                svc_host.setdefault('children', self._hosts(service_children,
                                                            dynamic))
                svc_host_vars.setdefault('ansible_ssh_user',
                                         self.ansible_ssh_user)
                if self.ansible_python_interpreter:
                    svc_host_vars.setdefault('ansible_python_interpreter',
                                             self.ansible_python_interpreter)

        excluded_hosts = self.stack_outputs.get('BlacklistedHostnames', {})
        excluded_overcloud = ret.setdefault('excluded_overcloud', {})
        exclude = excluded_overcloud.setdefault('hosts', {})
        for hostname in excluded_hosts:
            if hostname:
                exclude[hostname] = {}

    def _get_neutron_data(self):
        if not self.connection:
            LOG.info("Session not set, neutron data will not be used to build "
                     "the inventory.")
            return

        try:
            tags_filter = ['tripleo_stack_name={}'.format(self.plan_name)]
            ports = list(self.connection.network.ports(tags=tags_filter))
            if not ports:
                return None

            # Filter tripleo_service_vip and tripleo_vip_net ports
            ports = [p for p in ports
                     if not any("tripleo_service_vip" in tag for tag in p.tags)
                     and not any("tripleo_vip_net" in tag for tag in p.tags)]

            # NOTE(hjensas): ctlplane ports created by THT Heat Server
            # resources, or nova less without --network-ports/--network-config
            # enabled, does not have the 'tripleo_stack_name' tag. We
            # shouldn't use neutron as a source if no ctlplane ports are
            # tagged with the 'tripleo_stack_name'.
            # See bug: https://bugs.launchpad.net/tripleo/+bug/1928926
            found_ctlplane_port = False
            ctlplane_net = self.connection.network.find_network(
                self.host_network)
            if ctlplane_net:
                for p in ports:
                    if p.network_id == ctlplane_net.id:
                        found_ctlplane_port = True
                        break
            else:
                LOG.warning("Host SSH network %s not found in neutron, not "
                            "using neutron data for inventory",
                            self.host_network)
            if not found_ctlplane_port:
                return None

            networks = [self.connection.network.find_network(p.network_id)
                        for p in ports]
            subnets = []
            for net in networks:
                subnets.extend(self.connection.network.subnets(
                    network_id=net.id))

            data = NeutronData(networks, subnets, ports)
        except exception.MissingMandatoryNeutronResourceTag:
            # In case of missing required tags, neutron is useless as an
            # inventory source, log warning and return None to disable the
            # neutron source.
            LOG.warning("Neutron resource without mandatory tags present. "
                        "Disabling use of neutron as a source for inventory "
                        "generation.")
            return None
        except (openstack.connection.exceptions.EndpointNotFound,
                openstack.exceptions.ResourceNotFound,
                keystoneauth1.exceptions.catalog.EndpointNotFound):
            LOG.warning("Neutron service not installed. Disabling use of "
                        "neutron as a source for inventory generation.")
            return None

        return data

    def _add_host_from_neutron_data(self, host, ports, role_networks,
                                    role_vars):
        for port in ports:
            net_name = port['network_name']

            # Add network name to tripleo_role_networks variable
            if net_name not in role_networks:
                role_networks.append(net_name)

            # Append to role_vars if not already present
            net_config_keys = {'cidr', 'dns_nameservers', 'gateway_ip',
                               'host_routes', 'vlan_id'}
            for key in net_config_keys:
                var = '{}_{}'.format(net_name, key)
                if var not in role_vars:
                    role_vars.setdefault(var, port[key])

            # Add variable for hostname on network
            host.setdefault('{}_hostname'.format(net_name), '.'.join(
                [port['hostname'], port['dns_domain']]))

            # Add variable for IP address on networks
            host.setdefault('{}_ip'.format(net_name), port['ip_address'])

            if net_name == self.host_network:
                # Add variable for ansible_host
                host.setdefault('ansible_host', port['ip_address'])

                # Add variable for canonical hostname
                dns_domain = port.get('dns_domain')
                if dns_domain:
                    canonical_dns_domain = dns_domain.partition('.')[-1]
                else:
                    canonical_dns_domain = DEFAULT_DOMAIN
                host.setdefault('canonical_hostname', '.'.join(
                    [port['hostname'], canonical_dns_domain]))

    def _inventory_from_neutron_data(self, ret, children, dynamic):
        if not self.neutron_data:
            return
        ports_by_role_and_host = self.neutron_data.ports_by_role_and_host
        networks_by_id = self.neutron_data.networks_by_id

        netname_by_idx = {
            net['tags'].get('tripleo_net_idx'):
                net['tags'].get('tripleo_network_name')
            for _, net in networks_by_id.items()
            if net['name'] != self.host_network}
        networks_all = [netname_by_idx[idx] for idx in sorted(netname_by_idx)]
        networks_lower = {net['name_upper']: net['name']
                          for _, net in networks_by_id.items()}
        networks_upper = {net['name']: net['name_upper']
                          for _, net in networks_by_id.items()}

        for role_name, ports_by_host in ports_by_role_and_host.items():
            role = ret.setdefault(role_name, {})
            hosts = role.setdefault('hosts', {})
            role_vars = role.setdefault('vars', {})
            role_vars.setdefault('tripleo_role_name', role_name)
            role_vars.setdefault('ansible_ssh_user', self.ansible_ssh_user)
            role_vars.setdefault('serial', self.serial)
            role_networks = role_vars.setdefault('tripleo_role_networks', [])
            for hostname, ports in ports_by_host.items():
                host = hosts.setdefault(hostname, {})
                self._add_host_from_neutron_data(host, ports, role_networks,
                                                 role_vars)

            # The nic config templates use ctlplane_subnet_cidr, not
            # ctlplane_cidr. Handle the special case.
            role_vars.setdefault(self.host_network + '_subnet_cidr',
                                 role_vars[self.host_network + '_cidr'])
            role_vars.setdefault('tripleo_role_networks',
                                 sorted(role_networks))
            role_vars.setdefault(
                'role_networks',
                [networks_upper[net] for net in role_networks
                 if net != self.host_network])
            role_vars.setdefault('networks_all', networks_all)
            role_vars.setdefault('networks_lower', networks_lower)

            for _, net in networks_by_id.items():
                role_vars.setdefault(net['name'] + '_mtu', net['mtu'])

            children.add(role_name)
            self.hostvars.update(hosts)

            if dynamic:
                hosts_format = [h for h in hosts.keys()]
                hosts_format.sort()
                ret[role_name]['hosts'] = hosts_format

        if children:
            ret.setdefault(
                self.plan_name, {
                    'children': self._hosts(sorted(children), dynamic)
                }
            )
            ret.setdefault(
                'allovercloud', {
                    'children': self._hosts([self.plan_name], dynamic)
                }
            )

    def _extend_inventory(self, ret, dynamic, data=None):
        if not data:
            return

        for role_name, role_values in data.items():
            inventory_role = ret.get(role_name)
            if not inventory_role:
                continue
            inventory_hosts = inventory_role.get('hosts', {})
            inventory_vars = inventory_role.get('vars', {})

            config_file_hosts = role_values.get('hosts', {})
            config_file_vars = role_values.get('vars', {})

            for k, v in config_file_vars.items():
                inventory_vars.setdefault(k, v)

            for config_file_host, host_values in config_file_hosts.items():
                inventory_host = inventory_hosts.get(config_file_host, {})
                if not inventory_host:
                    continue

                for k, v in host_values.items():
                    inventory_host.setdefault(k, v)

            self.hostvars.update(inventory_hosts)
            if dynamic:
                hosts_format = [h for h in inventory_hosts.keys()]
                hosts_format.sort()
                ret[role_name]['hosts'] = hosts_format

    def _get_data_from_config_file(self):
        if not self.plan_name:
            return
        if not self.work_dir:
            return

        data_file_path = os.path.join(self.work_dir,
                                      constants.INVENTORY_NETWORK_CONFIG_FILE)
        if not os.path.isfile(data_file_path):
            return
        with open(data_file_path, 'r') as f:
            data = yaml.safe_load(f.read())

        return data

    def _undercloud_inventory(self, ret, dynamic):
        undercloud = ret.setdefault('Undercloud', {})
        undercloud.setdefault('hosts', self._hosts(['undercloud'], dynamic))
        _vars = undercloud.setdefault('vars', {})
        _vars.setdefault('ansible_host', 'localhost')
        _vars.setdefault('ansible_connection', self.undercloud_connection)
        # see https://github.com/ansible/ansible/issues/41808
        _vars.setdefault('ansible_remote_tmp', '/tmp/ansible-${USER}')
        # We don't want to let UC fail, especially when it comes to
        # external tasks.
        # See https://bugs.launchpad.net/tripleo/+bug/1960518 for context
        _vars.setdefault('any_error_fatal', True)
        _vars.setdefault('max_fail_percentage', 0)

        if self.ansible_python_interpreter:
            _vars.setdefault('ansible_python_interpreter',
                             self.ansible_python_interpreter)
        else:
            _vars.setdefault('ansible_python_interpreter', sys.executable)

        if self.undercloud_connection == UNDERCLOUD_CONNECTION_SSH:
            _vars.setdefault('ansible_ssh_user', self.ansible_ssh_user)
            if self.undercloud_key_file:
                _vars.setdefault('ansible_ssh_private_key_file',
                                 self.undercloud_key_file)

        _vars.setdefault('undercloud_service_list',
                         self.get_undercloud_service_list())

        # Remaining variables need the stack to be resolved ...
        if not self.stack:
            return

        _vars.setdefault('plan', self.plan_name)

        admin_password = self.get_overcloud_environment().get(
            'parameter_defaults', {}).get('AdminPassword')
        if admin_password:
            _vars.setdefault('overcloud_admin_password', admin_password)

        keystone_url = self.stack_outputs.get('KeystoneURL')
        if keystone_url:
            _vars.setdefault('overcloud_keystone_url', keystone_url)

        endpoint_map = self.stack_outputs.get('EndpointMap')
        if endpoint_map:
            horizon_endpoint = endpoint_map.get('HorizonPublic', {}).get('uri')
            if horizon_endpoint:
                _vars.setdefault('overcloud_horizon_url', horizon_endpoint)

    def list(self, dynamic=True):
        ret = OrderedDict()
        if dynamic:
            # Prevent Ansible from repeatedly calling us to get empty host
            # details
            ret.setdefault('_meta', {'hostvars': self.hostvars})

        children = set()

        self.stack = self._get_stack()
        self.stack_outputs = StackOutputs(self.stack)

        self.neutron_data = self._get_neutron_data()

        if self.stack is None and self.neutron_data is None:
            LOG.warning("Stack not found: %s. No data found in neither "
                        "neutron or heat. Only the undercloud will be added "
                        "to the inventory.", self.plan_name)

        self._undercloud_inventory(ret, dynamic)
        self._inventory_from_neutron_data(ret, children, dynamic)
        self._inventory_from_heat_outputs(ret, children, dynamic)
        self._extend_inventory(ret, dynamic,
                               data=self._get_data_from_config_file())

        return ret

    def host(self):
        # NOTE(mandre)
        # Dynamic inventory scripts must return empty json if they don't
        # provide detailed info for hosts:
        # http://docs.ansible.com/ansible/developing_inventory.html
        return {}

    def write_static_inventory(self, inventory_file_path, extra_vars=None):
        """Convert inventory list to static yaml format in a file."""
        allowed_extensions = ('.yaml', '.yml', '.json')
        if not os.path.splitext(inventory_file_path)[1] in allowed_extensions:
            raise ValueError("Path %s does not end with one of %s extensions"
                             % (inventory_file_path,
                                ",".join(allowed_extensions)))

        # For some reason the json/yaml format needed for static and
        # dynamic inventories is different for the hosts/children?!
        inventory = self.list(dynamic=False)

        if extra_vars:
            for var, value in extra_vars.items():
                if var in inventory:
                    inventory[var]['vars'].update(value)

        # Atomic update as concurrent tripleoclient commands can call this
        inventory_file_dir = os.path.dirname(inventory_file_path)
        with tempfile.NamedTemporaryFile(
                'w',
                dir=inventory_file_dir,
                delete=False) as inventory_file:
            yaml.dump(inventory, inventory_file, TemplateDumper)
        os.rename(inventory_file.name, inventory_file_path)


def generate_tripleo_ansible_inventory(heat=None,
                                       auth_url=None,
                                       username=None,
                                       project_name=None,
                                       cacert=None,
                                       plan='overcloud',
                                       work_dir=None,
                                       ansible_python_interpreter=None,
                                       ansible_ssh_user='tripleo-admin',
                                       undercloud_key_file=None,
                                       ssh_network='ctlplane',
                                       session=None,
                                       cloud_name='undercloud'):
    if not work_dir:
        work_dir = os.path.join(os.path.expanduser('~'),
                                'overcloud-deploy-{}'.format(plan))
    if not os.path.isdir(work_dir):
        work_dir = tempfile.mkdtemp(prefix='tripleo-ansible')

    inventory_path = os.path.join(
        work_dir, 'tripleo-ansible-inventory.yaml')
    inv = inventories.TripleoInventories({
        plan: TripleoInventory(
            cloud_name=cloud_name,
            hclient=heat,
            session=session,
            ansible_ssh_user=ansible_ssh_user,
            undercloud_key_file=undercloud_key_file,
            ansible_python_interpreter=ansible_python_interpreter,
            plan_name=plan,
            host_network=ssh_network,
            work_dir=work_dir
        )
    })

    inv.write_static_inventory(inventory_path)
    return inventory_path
