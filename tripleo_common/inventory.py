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

from heatclient.exc import HTTPNotFound

HOST_NETWORK = 'ctlplane'


class StackOutputs(object):
    """Item getter for stack outputs.

    It takes a long time to resolve stack outputs.  This class ensures that
    we only have to do it once and then reuse the results from that call in
    subsequent lookups.  It also lazy loads the outputs so we don't spend time
    on unnecessary Heat calls.
    """

    def __init__(self, plan, hclient):
        self.plan = plan
        self.outputs = {}
        self.hclient = hclient
        self.stack = None

    def _load_outputs(self):
        """Load outputs from the stack if necessary

        Retrieves the stack outputs if that has not already happened.  If it
        has then this is a noop.

        Sets the outputs to an empty dict if the stack is not found.
        """
        if not self.stack:
            try:
                self.stack = self.hclient.stacks.get(self.plan)
            except HTTPNotFound:
                self.outputs = {}
                return
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
    def __init__(self, configs, session, hclient):
        self.configs = configs
        self.session = session
        self.hclient = hclient
        self.stack_outputs = StackOutputs(self.configs.plan, self.hclient)

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
            environment = self.hclient.stacks.environment(self.configs.plan)
            return environment
        except HTTPNotFound:
            return {}

    UNDERCLOUD_SERVICES = [
        'openstack-nova-compute', 'openstack-heat-engine',
        'openstack-ironic-conductor', 'openstack-swift-container',
        'openstack-swift-object', 'openstack-mistral-engine']

    def get_undercloud_service_list(self):
        """Return list of undercloud services - currently static

        Replace this when we have a better way - e.g. heat deploys undercloud
        """
        return self.UNDERCLOUD_SERVICES

    def list(self):
        ret = OrderedDict({
            'undercloud': {
                'hosts': ['localhost'],
                'vars': {
                    'ansible_connection': 'local',
                    'auth_url': self.configs.auth_url,
                    'cacert': self.configs.cacert,
                    'os_auth_token': self.session.get_token(),
                    'plan': self.configs.plan,
                    'project_name': self.configs.project_name,
                    'username': self.configs.username,
                },
            }
        })

        swift_url = self.session.get_endpoint(service_type='object-store',
                                              interface='public')
        if swift_url:
            ret['undercloud']['vars']['undercloud_swift_url'] = swift_url

        keystone_url = self.stack_outputs.get('KeystoneURL')
        if keystone_url:
            ret['undercloud']['vars']['overcloud_keystone_url'] = keystone_url
        admin_password = self.get_overcloud_environment().get(
            'parameter_defaults', {}).get('AdminPassword')
        if admin_password:
            ret['undercloud']['vars']['overcloud_admin_password'] =\
                admin_password
        endpoint_map = self.stack_outputs.get('EndpointMap')

        ret['undercloud']['vars']['undercloud_service_list'] = \
            self.get_undercloud_service_list()

        if endpoint_map:
            horizon_endpoint = endpoint_map.get('HorizonPublic', {}).get('uri')
            if horizon_endpoint:
                ret['undercloud']['vars']['overcloud_horizon_url'] =\
                    horizon_endpoint

        role_net_ip_map = self.stack_outputs.get('RoleNetIpMap', {})
        role_node_id_map = self.stack_outputs.get('ServerIdData', {})
        networks = set()
        role_net_hostname_map = self.stack_outputs.get(
            'RoleNetHostnameMap', {})
        children = []
        for role, hostnames in role_net_hostname_map.items():
            if hostnames:
                names = hostnames.get(HOST_NETWORK) or []
                shortnames = [n.split(".%s." % HOST_NETWORK)[0] for n in names]
                # Create a group per hostname to map hostname to IP
                ips = role_net_ip_map[role][HOST_NETWORK]
                for idx, name in enumerate(shortnames):
                    ret[name] = {'hosts': [ips[idx]]}
                    if 'server_ids' in role_node_id_map:
                        ret[name]['vars'] = {
                            'deploy_server_id': role_node_id_map[
                                'server_ids'][role][idx]}
                    # Add variable for listing enabled networks in the node
                    ret[name]['vars']['enabled_networks'] = \
                        [str(net) for net in role_net_ip_map[role]]
                    # Add variable for IP on each network
                    for net in role_net_ip_map[role]:
                        ret[name]['vars']["%s_ip" % net] = \
                            role_net_ip_map[role][net][idx]
                    networks.update(ret[name]['vars']['enabled_networks'])

                children.append(role)
                ret[role] = {
                    'children': sorted(shortnames),
                    'vars': {
                        'ansible_ssh_user': self.configs.ansible_ssh_user,
                        'bootstrap_server_id': role_node_id_map.get(
                            'bootstrap_server_id'),
                        'role_name': role,
                    }
                }

        if children:
            vip_map = self.stack_outputs.get('VipMap', {})
            vips = {(vip_name + "_vip"): vip
                    for vip_name, vip in vip_map.items()
                    if vip and (vip_name in networks or vip_name == 'redis')}
            ret['overcloud'] = {
                'children': sorted(children),
                'vars': vips
            }

        # Associate services with roles
        roles_by_service = self.get_roles_by_service(
            self.stack_outputs.get('EnabledServices', {}))
        for service, roles in roles_by_service.items():
            service_children = [role for role in roles
                                if ret.get(role) is not None]
            if service_children:
                ret[service.lower()] = {
                    'children': service_children,
                    'vars': {
                        'ansible_ssh_user': self.configs.ansible_ssh_user
                    }
                }

        # Prevent Ansible from repeatedly calling us to get empty host details
        ret['_meta'] = {'hostvars': {}}

        return ret

    def host(self):
        # NOTE(mandre)
        # Dynamic inventory scripts must return empty json if they don't
        # provide detailed info for hosts:
        # http://docs.ansible.com/ansible/developing_inventory.html
        return {}
