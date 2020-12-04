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
import logging
import os
import sys
import tempfile
import yaml

from heatclient.exc import HTTPNotFound

HOST_NETWORK = 'ctlplane'

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


class TripleoInventory(object):
    def __init__(self, session=None, hclient=None,
                 plan_name=None, auth_url=None, project_name=None,
                 cacert=None, username=None, ansible_ssh_user=None,
                 host_network=None, ansible_python_interpreter=None,
                 undercloud_connection=UNDERCLOUD_CONNECTION_LOCAL,
                 undercloud_key_file=None, serial=1):
        self.hclient = hclient
        self.host_network = host_network or HOST_NETWORK
        self.auth_url = auth_url
        self.cacert = cacert
        self.project_name = project_name
        self.username = username
        self.ansible_ssh_user = ansible_ssh_user
        self.undercloud_key_file = undercloud_key_file
        self.plan_name = plan_name
        self.ansible_python_interpreter = ansible_python_interpreter
        self.hostvars = {}
        self.undercloud_connection = undercloud_connection
        self.serial = serial

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
        except HTTPNotFound:
            return {}

    UNDERCLOUD_SERVICES = [
        'tripleo_nova_compute', 'tripleo_heat_engine',
        'tripleo_ironic_conductor', 'tripleo_swift_container_server',
        'tripleo_swift_object_server', 'tripleo_mistral_engine']

    def get_undercloud_service_list(self):
        """Return list of undercloud services - currently static

        Replace this when we have a better way - e.g. heat deploys undercloud
        """
        return self.UNDERCLOUD_SERVICES

    def _hosts(self, alist, dynamic=True):
        """Static yaml inventories reqire a different hosts format?!"""
        if not dynamic:
            return {x: {} for x in alist}
        else:
            return alist

    def _get_stack(self):
        if self.plan_name is None:
            return None
        try:
            stack = self.hclient.stacks.get(self.plan_name)
        except HTTPNotFound:
            LOG.warning("Stack not found: %s. Only the undercloud will "
                        "be added to the inventory." % self.plan_name)
            stack = None

        return stack

    def list(self, dynamic=True):
        ret = OrderedDict({
            'Undercloud': {
                'hosts': self._hosts(['undercloud'], dynamic),
                'vars': {
                    'ansible_host': 'localhost',
                    'ansible_python_interpreter': sys.executable,
                    'ansible_connection': self.undercloud_connection,
                    # see https://github.com/ansible/ansible/issues/41808
                    'ansible_remote_tmp': '/tmp/ansible-${USER}',
                    'auth_url': self.auth_url,
                    'plan': None,
                    'project_name': self.project_name,
                    'username': self.username,
                },
            }
        })

        if self.cacert:
            ret['Undercloud']['vars']['cacert'] = \
                self.cacert

        if self.ansible_python_interpreter:
            ret['Undercloud']['vars']['ansible_python_interpreter'] = \
                self.ansible_python_interpreter

        if self.undercloud_connection == UNDERCLOUD_CONNECTION_SSH:
            ret['Undercloud']['vars']['ansible_ssh_user'] = \
                self.ansible_ssh_user
            if self.undercloud_key_file:
                ret['Undercloud']['vars']['ansible_ssh_private_key_file'] = \
                    self.undercloud_key_file

        ret['Undercloud']['vars']['undercloud_service_list'] = \
            self.get_undercloud_service_list()

        if dynamic:
            # Prevent Ansible from repeatedly calling us to get empty host
            # details
            ret['_meta'] = {'hostvars': self.hostvars}

        self.stack = self._get_stack()
        if not self.stack:
            return ret

        ret['Undercloud']['vars']['plan'] = self.plan_name
        admin_password = self.get_overcloud_environment().get(
            'parameter_defaults', {}).get('AdminPassword')
        if admin_password:
            ret['Undercloud']['vars']['overcloud_admin_password'] =\
                admin_password

        self.stack_outputs = StackOutputs(self.stack)

        keystone_url = self.stack_outputs.get('KeystoneURL')
        if keystone_url:
            ret['Undercloud']['vars']['overcloud_keystone_url'] = keystone_url

        endpoint_map = self.stack_outputs.get('EndpointMap')
        if endpoint_map:
            horizon_endpoint = endpoint_map.get('HorizonPublic', {}).get('uri')
            if horizon_endpoint:
                ret['Undercloud']['vars']['overcloud_horizon_url'] =\
                    horizon_endpoint

        role_net_ip_map = self.stack_outputs.get('RoleNetIpMap', {})
        role_node_id_map = self.stack_outputs.get('ServerIdData', {})
        networks = set()
        role_net_hostname_map = self.stack_outputs.get(
            'RoleNetHostnameMap', {})
        children = []
        for role, hostnames in role_net_hostname_map.items():
            if hostnames:
                names = hostnames.get(self.host_network) or []
                shortnames = [n.split(".%s." % self.host_network)[0].lower()
                              for n in names]
                ips = role_net_ip_map[role][self.host_network]
                if not ips:
                    raise Exception("No IPs found for %s role on %s network"
                                    % (role, self.host_network))
                hosts = {}
                for idx, name in enumerate(shortnames):
                    hosts[name] = {}
                    hosts[name].update({
                        'ansible_host': ips[idx]})
                    if 'server_ids' in role_node_id_map:
                        hosts[name].update({
                            'deploy_server_id': role_node_id_map[
                                'server_ids'][role][idx]})
                    # Add variable for IP on each network
                    for net in role_net_ip_map[role]:
                        hosts[name].update({
                            "%s_ip" % net:
                                role_net_ip_map[role][net][idx]})
                    # Add variables for hostname on each network
                    for net in role_net_hostname_map[role]:
                        hosts[name].update({
                            "%s_hostname" % net:
                                role_net_hostname_map[role][net][idx]})

                children.append(role)

                if not dynamic:
                    hosts_format = hosts
                else:
                    hosts_format = [h for h in hosts.keys()]
                    hosts_format.sort()

                role_networks = sorted([
                    str(net) for net in role_net_ip_map[role]
                ])
                networks.update(role_networks)

                ret[role] = {
                    'hosts': hosts_format,
                    'vars': {
                        'ansible_ssh_user': self.ansible_ssh_user,
                        'bootstrap_server_id': role_node_id_map.get(
                            'bootstrap_server_id'),
                        'tripleo_role_name': role,
                        'tripleo_role_networks': role_networks,
                        'serial': self.serial,
                    }

                }

                if self.ansible_python_interpreter:
                    ret[role]['vars']['ansible_python_interpreter'] = \
                        self.ansible_python_interpreter

                self.hostvars.update(hosts)

        if children:
            vip_map = self.stack_outputs.get('VipMap', {})
            overcloud_vars = {
                (vip_name + "_vip"): vip for vip_name, vip in vip_map.items()
                if vip and (vip_name in networks or vip_name == 'redis')
            }

            overcloud_vars['container_cli'] = \
                self.get_overcloud_environment().get(
                    'parameter_defaults', {}).get('ContainerCli')

            ret['allovercloud'] = {
                'children': self._hosts(sorted(children), dynamic),
                'vars': overcloud_vars
            }

            ret[self.plan_name] = {
                'children': self._hosts(['allovercloud'], dynamic)
            }
            if self.plan_name != 'overcloud':
                ret['overcloud'] = {
                    'children': self._hosts(['allovercloud'], dynamic),
                    'deprecated': 'Deprecated by allovercloud group in Ussuri'
                }

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
                svc_host = service.lower()
                ret[svc_host] = {
                    'children': self._hosts(service_children, dynamic),
                    'vars': {
                        'ansible_ssh_user': self.ansible_ssh_user
                    }
                }
                if self.ansible_python_interpreter:
                    ret[svc_host]['vars']['ansible_python_interpreter'] = \
                        self.ansible_python_interpreter

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


def generate_tripleo_ansible_inventory(heat, auth,
                                       cacert=None,
                                       plan='overcloud',
                                       work_dir=None,
                                       ansible_python_interpreter=None,
                                       ansible_ssh_user='tripleo-admin',
                                       undercloud_key_file=None,
                                       ssh_network='ctlplane'):
    if not work_dir:
        work_dir = tempfile.mkdtemp(prefix='tripleo-ansible')

    inventory_path = os.path.join(
        work_dir, 'tripleo-ansible-inventory.yaml')
    inv = TripleoInventory(
        hclient=heat,
        auth_url=auth.auth_uri,
        cacert=cacert,
        project_name=auth.project_name,
        username=auth.user_name,
        ansible_ssh_user=ansible_ssh_user,
        undercloud_key_file=undercloud_key_file,
        ansible_python_interpreter=ansible_python_interpreter,
        plan_name=plan,
        host_network=ssh_network)

    inv.write_static_inventory(inventory_path)
    return inventory_path
