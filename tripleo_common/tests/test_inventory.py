# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import fixtures
import os
import yaml

from heatclient.exc import HTTPNotFound
from mock import MagicMock

from tripleo_common.inventory import StackOutputs
from tripleo_common.inventory import TripleoInventory
from tripleo_common.tests import base


MOCK_ENABLED_SERVICES = {
    "ObjectStorage": [
        "kernel",
        "swift_storage",
        "tripleo_packages"
    ],
    "Controller": [
        "kernel",
        "keystone",
        "tripleo_packages"
    ],
    "Compute": [
        "nova_compute",
        "kernel",
        "tripleo_packages"
    ],
    "CephStorage": [
        "kernel",
        "tripleo_packages"
    ],
    "BlockStorage": [
        "cinder_volume",
        "kernel",
        "tripleo_packages"
    ]
}


class TestInventory(base.TestCase):
    def setUp(self):
        super(TestInventory, self).setUp()
        self.outputs_data = {'outputs': [
            {'output_key': 'EnabledServices',
             'output_value': {
                 'Controller': ['sa', 'sb'],
                 'Compute': ['sd', 'se'],
                 'CustomRole': ['sg', 'sh']}},
            {'output_key': 'KeystoneURL',
             'output_value': 'xyz://keystone'},
            {'output_key': 'ServerIdData',
             'output_value': {
                 'server_ids': {
                     'Controller': ['a', 'b', 'c'],
                     'Compute': ['d'],
                     'CustomRole': ['e']},
                 'bootstrap_server_id': 'a'}},
            {'output_key': 'RoleNetHostnameMap',
             'output_value': {
                 'Controller': {
                     'ctlplane': ['c-0.ctlplane.localdomain',
                                  'c-1.ctlplane.localdomain',
                                  'c-2.ctlplane.localdomain']},
                 'Compute': {
                     'ctlplane': ['cp-0.ctlplane.localdomain']},
                 'CustomRole': {
                     'ctlplane': ['cs-0.ctlplane.localdomain']}}},
            {'output_key': 'RoleNetIpMap',
             'output_value': {
                 'Controller': {
                     'ctlplane': ['x.x.x.1',
                                  'x.x.x.2',
                                  'x.x.x.3']},
                 'Compute': {
                     'ctlplane': ['y.y.y.1']},
                 'CustomRole': {
                     'ctlplane': ['z.z.z.1']}}},
            {'output_key': 'VipMap',
             'output_value': {
                 'ctlplane': 'x.x.x.4',
                 'redis': 'x.x.x.6'}},
            {'output_key': 'RoleData',
             'output_value': {
                 'Controller': {'config_settings': 'foo1'},
                 'Compute': {'config_settings': 'foo2'},
                 'CustomRole': {'config_settings': 'foo3'}}}]}
        self.plan_name = 'overcloud'

        self.hclient = MagicMock()
        self.hclient.stacks.environment.return_value = {
            'parameter_defaults': {'AdminPassword': 'theadminpw'}}
        self.mock_stack = MagicMock()
        self.mock_stack.outputs = self.outputs_data['outputs']
        self.hclient.stacks.get.return_value = self.mock_stack

        self.session = MagicMock()
        self.session.get_token.return_value = 'atoken'
        self.session.get_endpoint.return_value = 'anendpoint'

        self.outputs = StackOutputs('overcloud', self.hclient)
        self.inventory = TripleoInventory(
            session=self.session,
            hclient=self.hclient,
            plan_name=self.plan_name,
            auth_url='xyz://keystone.local',
            cacert='acacert',
            project_name='admin',
            username='admin',
            ansible_ssh_user='heat-admin')
        self.inventory.stack_outputs = self.outputs

    def test_get_roles_by_service(self):
        services = TripleoInventory.get_roles_by_service(
            MOCK_ENABLED_SERVICES)
        expected = {
            'kernel': ['BlockStorage', 'CephStorage', 'Compute', 'Controller',
                       'ObjectStorage'],
            'swift_storage': ['ObjectStorage'],
            'tripleo_packages': ['BlockStorage', 'CephStorage', 'Compute',
                                 'Controller', 'ObjectStorage'],
            'keystone': ['Controller'],
            'nova_compute': ['Compute'],
            'cinder_volume': ['BlockStorage'],
        }
        self.assertDictEqual(services, expected)

    def test_outputs_are_empty_if_stack_doesnt_exist(self):
        self.hclient.stacks.get.side_effect = HTTPNotFound('not found')
        stack_outputs = StackOutputs('no-plan', self.hclient)
        self.assertEqual(list(stack_outputs), [])

    def test_outputs_valid_key_calls_api(self):
        expected = 'xyz://keystone'
        self.hclient.stacks.output_show.return_value = dict(output=dict(
            output_value=expected))
        self.assertEqual(expected, self.outputs['KeystoneURL'])
        # This should also support the get method
        self.assertEqual(expected, self.outputs.get('KeystoneURL'))
        self.assertTrue(self.hclient.called_once_with('overcloud',
                                                      'KeystoneURL'))

    def test_outputs_invalid_key_raises_keyerror(self):
        self.assertRaises(KeyError, lambda: self.outputs['Invalid'])

    def test_outputs_get_method_returns_default(self):
        default = 'default value'
        self.assertEqual(default, self.outputs.get('Invalid', default))

    def test_outputs_iterating_returns_list_of_output_keys(self):
        self.assertEqual(
            {'EnabledServices', 'KeystoneURL', 'ServerIdData',
             'RoleNetHostnameMap', 'RoleNetIpMap', 'VipMap',
             'RoleData'},
            set([o for o in self.outputs]))

    def test_inventory_list(self):
        self._inventory_list(self.inventory)

    def test_inventory_list_backwards_compat_configs(self):
        # FIXME(shardy) backwards compatibility until we switch
        # tripleo-validations to pass the individual values
        configs = MagicMock()
        configs.plan = self.plan_name
        configs.auth_url = 'xyz://keystone.local'
        configs.cacert = 'acacert'
        configs.project_name = 'admin'
        configs.username = 'admin'
        configs.ansible_ssh_user = 'heat-admin'
        inventory = TripleoInventory(
            configs, self.session, self.hclient)
        self._inventory_list(inventory)

    def _inventory_list(self, inventory):
        ansible_ssh_user = 'heat-admin'
        expected = {
            'Compute': {
                'hosts': ['cp-0'],
                'vars': {'ansible_ssh_user': ansible_ssh_user,
                         'bootstrap_server_id': 'a',
                         'role_name': 'Compute',
                         'tripleo_role_name': 'Compute'}},
            'Controller': {
                'hosts': ['c-0', 'c-1', 'c-2'],
                'vars': {'ansible_ssh_user': ansible_ssh_user,
                         'bootstrap_server_id': 'a',
                         'role_name': 'Controller',
                         'tripleo_role_name': 'Controller'}},
            'CustomRole': {
                'hosts': ['cs-0'],
                'vars': {'ansible_ssh_user': ansible_ssh_user,
                         'bootstrap_server_id': 'a',
                         'role_name': 'CustomRole',
                         'tripleo_role_name': 'CustomRole'}},

            'overcloud': {
                'children': ['Compute', 'Controller', 'CustomRole'],
                'vars': {
                    'ctlplane_vip': 'x.x.x.4',
                    'redis_vip': 'x.x.x.6'}},
            'Undercloud': {
                'hosts': ['undercloud'],
                'vars': {'ansible_connection': 'local',
                         'ansible_host': 'localhost',
                         'ansible_remote_tmp': '/tmp/ansible-${USER}',
                         'auth_url': 'xyz://keystone.local',
                         'cacert': 'acacert',
                         'os_auth_token': 'atoken',
                         'overcloud_keystone_url': 'xyz://keystone',
                         'overcloud_admin_password': 'theadminpw',
                         'plan': 'overcloud',
                         'project_name': 'admin',
                         'undercloud_service_list': [
                             'openstack-nova-compute',
                             'openstack-heat-engine',
                             'openstack-ironic-conductor',
                             'openstack-swift-container',
                             'openstack-swift-object',
                             'openstack-mistral-engine'],
                         'undercloud_swift_url': 'anendpoint',
                         'username': 'admin'}}}
        inv_list = inventory.list()
        for k in expected:
            self.assertEqual(expected[k], inv_list[k])

    def test_ansible_ssh_user(self):
        self._try_alternative_args(
            ansible_ssh_user='my-custom-admin',
            session=self.session,)

    def test_no_session(self):
        self._try_alternative_args(
            ansible_ssh_user='my-custom-admin',
            session=None)

    def _try_alternative_args(self, ansible_ssh_user, session):
        self.inventory = TripleoInventory(
            session=session,
            hclient=self.hclient,
            plan_name=self.plan_name,
            auth_url='xyz://keystone.local',
            project_name='admin',
            username='admin',
            cacert='acacert',
            ansible_ssh_user=ansible_ssh_user)

        self.inventory.stack_outputs = self.outputs

        expected = {
            'Compute': {
                'hosts': ['cp-0'],
                'vars': {'ansible_ssh_user': ansible_ssh_user,
                         'bootstrap_server_id': 'a',
                         'role_name': 'Compute',
                         'tripleo_role_name': 'Compute'}},
            'Controller': {
                'hosts': ['c-0', 'c-1', 'c-2'],
                'vars': {'ansible_ssh_user': ansible_ssh_user,
                         'bootstrap_server_id': 'a',
                         'role_name': 'Controller',
                         'tripleo_role_name': 'Controller'}},
            'CustomRole': {
                'hosts': ['cs-0'],
                'vars': {'ansible_ssh_user': ansible_ssh_user,
                         'bootstrap_server_id': 'a',
                         'role_name': 'CustomRole',
                         'tripleo_role_name': 'CustomRole'}},
            'overcloud': {
                'children': ['Compute', 'Controller', 'CustomRole'],
                'vars': {
                    'ctlplane_vip': 'x.x.x.4',
                    'redis_vip': 'x.x.x.6'}},
            'Undercloud': {
                'hosts': ['undercloud'],
                'vars': {'ansible_connection': 'local',
                         'ansible_host': 'localhost',
                         'ansible_remote_tmp': '/tmp/ansible-${USER}',
                         'auth_url': 'xyz://keystone.local',
                         'cacert': 'acacert',
                         'os_auth_token':
                         'atoken' if session else None,
                         'overcloud_keystone_url': 'xyz://keystone',
                         'overcloud_admin_password': 'theadminpw',
                         'plan': 'overcloud',
                         'project_name': 'admin',
                         'undercloud_service_list': [
                             'openstack-nova-compute',
                             'openstack-heat-engine',
                             'openstack-ironic-conductor',
                             'openstack-swift-container',
                             'openstack-swift-object',
                             'openstack-mistral-engine'],
                         'undercloud_swift_url':
                         'anendpoint' if session else None,
                         'username': 'admin'}}}

        inv_list = self.inventory.list()
        for k in expected:
            self.assertEqual(expected[k], inv_list[k])

    def test_inventory_write_static(self):
        self._inventory_write_static()

    def test_inventory_write_static_extra_vars(self):
        extra_vars = {'Undercloud': {'anextravar': 123}}
        self._inventory_write_static(extra_vars=extra_vars)

    def _inventory_write_static(self, extra_vars=None):
        tmp_dir = self.useFixture(fixtures.TempDir()).path
        inv_path = os.path.join(tmp_dir, "inventory.yaml")
        self.inventory.write_static_inventory(inv_path, extra_vars)
        ansible_ssh_user = 'heat-admin'
        expected = {
            'Compute': {
                'hosts': {
                    'cp-0': {
                        'ansible_host': 'y.y.y.1',
                        'ctlplane_ip': 'y.y.y.1',
                        'deploy_server_id': 'd',
                        'enabled_networks': ['ctlplane']}},
                'vars': {'ansible_ssh_user': ansible_ssh_user,
                         'bootstrap_server_id': 'a',
                         'role_name': 'Compute',
                         'tripleo_role_name': 'Compute'}},
            'Controller': {
                'hosts': {
                    'c-0': {
                        'ansible_host': 'x.x.x.1',
                        'ctlplane_ip': 'x.x.x.1',
                        'deploy_server_id': 'a',
                        'enabled_networks': ['ctlplane']},
                    'c-1': {
                        'ansible_host': 'x.x.x.2',
                        'ctlplane_ip': 'x.x.x.2',
                        'deploy_server_id': 'b',
                        'enabled_networks': ['ctlplane']},
                    'c-2': {
                        'ansible_host': 'x.x.x.3',
                        'ctlplane_ip': 'x.x.x.3',
                        'deploy_server_id': 'c',
                        'enabled_networks': ['ctlplane']}},
                'vars': {'ansible_ssh_user': ansible_ssh_user,
                         'bootstrap_server_id': 'a',
                         'role_name': 'Controller',
                         'tripleo_role_name': 'Controller'}},
            'CustomRole': {
                'hosts': {
                    'cs-0': {
                        'ansible_host': 'z.z.z.1',
                        'ctlplane_ip': 'z.z.z.1',
                        'deploy_server_id': 'e',
                        'enabled_networks': ['ctlplane']}},
                'vars': {'ansible_ssh_user': ansible_ssh_user,
                         'bootstrap_server_id': 'a',
                         'role_name': 'CustomRole',
                         'tripleo_role_name': 'CustomRole'}},
            'overcloud': {'children': {'Compute': {},
                                       'Controller': {},
                                       'CustomRole': {}},
                          'vars': {'ctlplane_vip': 'x.x.x.4',
                                   'redis_vip': 'x.x.x.6'}},
            'sa': {'children': {'Controller': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'sb': {'children': {'Controller': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'sd': {'children': {'Compute': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'se': {'children': {'Compute': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'sg': {'children': {'CustomRole': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'sh': {'children': {'CustomRole': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'Undercloud': {'hosts': {'undercloud': {}},
                           'vars': {'ansible_connection': 'local',
                                    'ansible_host': 'localhost',
                                    'ansible_remote_tmp':
                                        '/tmp/ansible-${USER}',
                                    'auth_url': 'xyz://keystone.local',
                                    'cacert': 'acacert',
                                    'os_auth_token': 'atoken',
                                    'overcloud_admin_password': 'theadminpw',
                                    'overcloud_keystone_url': 'xyz://keystone',
                                    'plan': 'overcloud',
                                    'project_name': 'admin',
                                    'undercloud_service_list': [
                                        'openstack-nova-compute',
                                        'openstack-heat-engine',
                                        'openstack-ironic-conductor',
                                        'openstack-swift-container',
                                        'openstack-swift-object',
                                        'openstack-mistral-engine'],
                                    'undercloud_swift_url': 'anendpoint',
                                    'username': 'admin'}}}
        if extra_vars:
            expected['Undercloud']['vars']['anextravar'] = 123

        with open(inv_path, 'r') as f:
            loaded_inv = yaml.safe_load(f)
        self.assertEqual(expected, loaded_inv)
