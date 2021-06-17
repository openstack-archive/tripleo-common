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

from collections import OrderedDict
import fixtures
import os
import sys
from unittest import mock

import yaml

from heatclient.exc import HTTPNotFound

from tripleo_common.inventory import NeutronData
from tripleo_common.inventory import StackOutputs
from tripleo_common.inventory import TripleoInventory
from tripleo_common.tests import base
from tripleo_common.tests.fake_neutron import fakes as neutron_fakes


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
        "tripleo_packages",
        "ceph_client"
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
            {
                'output_key': 'EnabledServices',
                'output_value': {
                    'Controller': ['sa', 'sb'],
                    'Compute': ['sd', 'se', 'ceph_client'],
                    'CustomRole': ['sg', 'sh']}
                },
            {
                'output_key': 'KeystoneURL',
                'output_value': 'xyz://keystone'
                },
            {
                'output_key': 'ServerIdData',
                'output_value': {
                    'server_ids': {
                        'Controller': ['a', 'b', 'c'],
                        'Compute': ['d'],
                        'CustomRole': ['e']
                        },
                    'bootstrap_server_id': 'a'
                    }
                },
            {
                'output_key': 'RoleNetHostnameMap',
                'output_value': {
                    'Controller': {
                        'ctlplane': [
                            'c-0.ctlplane.localdomain',
                            'c-1.ctlplane.localdomain',
                            'c-2.ctlplane.localdomain'],
                        'internal_api': [
                            'c-0.internal_api.localdomain',
                            'c-1.internal_api.localdomain',
                            'c-2.internal_api.localdomain']
                        },
                    'Compute': {
                        'ctlplane': ['cp-0.ctlplane.localdomain']
                        },
                    'CustomRole': {
                        'ctlplane': ['cs-0.ctlplane.localdomain']
                        }
                    }
                },
            {
                'output_key': 'RoleNetIpMap',
                'output_value': {
                    'Controller': {
                        'ctlplane': [
                            'x.x.x.1',
                            'x.x.x.2',
                            'x.x.x.3'
                            ],
                        'internal_api': [
                            'x.x.x.4',
                            'x.x.x.5',
                            'x.x.x.6'
                            ]
                        },
                    'Compute': {
                        'ctlplane': ['y.y.y.1']
                        },
                    'CustomRole': {
                        'ctlplane': ['z.z.z.1']
                        }
                    }
                },
            {
                'output_key': 'VipMap',
                'output_value': {
                    'ctlplane': 'x.x.x.4',
                    'redis': 'x.x.x.6'
                    }
                },
            {
                'output_key': 'RoleData',
                'output_value': {
                    'Controller': {'config_settings': 'foo1'},
                    'Compute': {'config_settings': 'foo2'},
                    'CustomRole': {'config_settings': 'foo3'}
                    }
                }
            ]
        }
        self.plan_name = 'overcloud'
        self.hclient = mock.MagicMock()
        self.hclient.stacks.environment.return_value = {
            'parameter_defaults': {
                'AdminPassword': 'theadminpw',
                'ContainerCli': 'podman'
                }
            }
        self.mock_stack = mock.MagicMock()
        self.mock_stack.outputs = self.outputs_data['outputs']
        self.hclient.stacks.get.return_value = self.mock_stack
        self.outputs = StackOutputs(self.mock_stack)
        self.connection = mock.MagicMock()
        patcher = mock.patch('openstack.connect',
                             return_value=self.connection)
        patcher.start()
        self.inventory = TripleoInventory(
            cloud_name='undercloud',
            hclient=self.hclient,
            plan_name=self.plan_name,
            ansible_ssh_user='heat-admin')
        self.inventory.stack_outputs = self.outputs
        self.addCleanup(patcher.stop)

    def test_get_roles_by_service(self):
        services = TripleoInventory.get_roles_by_service(MOCK_ENABLED_SERVICES)
        expected = {
            'kernel': [
                'BlockStorage',
                'CephStorage',
                'Compute',
                'Controller',
                'ObjectStorage'
                ],
            'swift_storage': ['ObjectStorage'],
            'tripleo_packages': [
                'BlockStorage',
                'CephStorage',
                'Compute',
                'Controller',
                'ObjectStorage'
                ],
            'keystone': ['Controller'],
            'nova_compute': ['Compute'],
            'cinder_volume': ['BlockStorage'],
            'ceph_client': ['Compute'],
        }
        self.assertDictEqual(services, expected)

    def test_stack_not_found(self):
        self.hclient.stacks.get.side_effect = HTTPNotFound('not found')
        self.assertEqual(None, self.inventory._get_stack())

    def test_outputs_valid_key_calls_api(self):
        expected = 'xyz://keystone'
        self.hclient.stacks.output_show.return_value = dict(output=dict(
            output_value=expected))
        self.assertEqual(expected, self.outputs['KeystoneURL'])
        # This should also support the get method
        self.assertEqual(expected, self.outputs.get('KeystoneURL'))
        self.assertTrue(self.hclient.called_once_with(
            'overcloud', 'KeystoneURL'))

    def test_no_ips(self):
        for output in self.outputs_data['outputs']:
            if output['output_key'] == 'RoleNetIpMap':
                output['output_value'] = dict(Controller=dict(ctlplane=[]))
        self.assertRaises(Exception, self.inventory.list)

    def test_outputs_invalid_key_raises_keyerror(self):
        self.assertRaises(KeyError, lambda: self.outputs['Invalid'])

    def test_outputs_get_method_returns_default(self):
        default = 'default value'
        self.assertEqual(default, self.outputs.get('Invalid', default))

    def test_outputs_iterating_returns_list_of_output_keys(self):
        self.assertEqual({
            'EnabledServices',
            'KeystoneURL',
            'ServerIdData',
            'RoleNetHostnameMap',
            'RoleNetIpMap',
            'VipMap',
            'RoleData'
        }, set([o for o in self.outputs]))

    def test_inventory_list(self):
        self.inventory.undercloud_connection = 'local'
        self._inventory_list(self.inventory)

    def _inventory_list(self, inventory):
        ansible_ssh_user = 'heat-admin'
        expected = {
            'Compute': {
                'hosts': ['cp-0'],
                'vars': {
                    'ansible_ssh_user': ansible_ssh_user,
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'Compute',
                    'tripleo_role_networks': ['ctlplane']
                    }
                },
            'Controller': {
                'hosts': ['c-0', 'c-1', 'c-2'],
                'vars': {
                    'ansible_ssh_user': ansible_ssh_user,
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'Controller',
                    'tripleo_role_networks': [
                        'ctlplane',
                        'internal_api'
                        ]
                    }
                },
            'CustomRole': {
                'hosts': ['cs-0'],
                'vars': {
                    'ansible_ssh_user': ansible_ssh_user,
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'CustomRole',
                    'tripleo_role_networks': ['ctlplane']
                    }
                },
            'overcloud': {
                'children': ['allovercloud']
                },
            'allovercloud': {
                'children': ['Compute', 'Controller', 'CustomRole'],
                'vars': {
                    'container_cli': 'podman',
                    'ctlplane_vip': 'x.x.x.4',
                    'redis_vip': 'x.x.x.6'
                    }
                },
            'Undercloud': {
                'hosts': ['undercloud'],
                'vars': {
                    'ansible_connection': 'local',
                    'ansible_host': 'localhost',
                    'ansible_python_interpreter': sys.executable,
                    'ansible_remote_tmp': '/tmp/ansible-${USER}',
                    'overcloud_keystone_url': 'xyz://keystone',
                    'overcloud_admin_password': 'theadminpw',
                    'plan': 'overcloud',
                    'undercloud_service_list': [
                        'tripleo_nova_compute',
                        'tripleo_heat_engine',
                        'tripleo_ironic_conductor',
                        'tripleo_swift_container_server',
                        'tripleo_swift_object_server',
                        'tripleo_mistral_engine'
                        ],
                    }
                }
            }
        inv_list = inventory.list()
        for k in expected:
            self.assertEqual(expected[k], inv_list[k])

    def test_inventory_list_undercloud_installer(self):
        outputs_data = {
            'outputs': [
                {'output_key': 'EnabledServices',
                 'output_value': {'Undercloud': ['sa', 'sb']}},
                {'output_key': 'KeystoneURL',
                 'output_value': 'xyz://keystone'},
                {'output_key': 'ServerIdData',
                 'output_value': {'server_ids': {'Undercloud': ['a']},
                                  'bootstrap_server_id': 'a'}},
                {'output_key': 'RoleNetHostnameMap',
                 'output_value': {'Undercloud': {
                     'ctlplane': ['uc0.ctlplane.localdomain'],
                     'external': ['uc0.external.localdomain'],
                     'canonical': ['uc0.lab.example.com']}}},
                {'output_key': 'RoleNetIpMap',
                 'output_value': {'Undercloud': {'ctlplane': ['x.x.x.1'],
                                                 'external': ['x.x.x.1']}}},
                {'output_key': 'VipMap',
                 'output_value': {'ctlplane': 'x.x.x.4', 'redis': 'x.x.x.6'}},
                {'output_key': 'RoleData',
                 'output_value': {'Undercloud': {'config_settings': 'foo1'}}}
            ]
        }

        self.hclient.stacks.environment.return_value = {
            'parameter_defaults': {
                'AdminPassword': 'theadminpw', 'ContainerCli': 'podman'}}
        mock_stack = mock.MagicMock()
        mock_stack.outputs = outputs_data['outputs']
        self.hclient.stacks.get.return_value = mock_stack

        outputs = StackOutputs(mock_stack)
        inventory = TripleoInventory(
            hclient=self.hclient,
            cloud_name='undercloud',
            plan_name='overcloud',
            ansible_ssh_user='heat-admin')
        inventory.stack_outputs = outputs
        expected = {
            'Undercloud': {
                'hosts': {
                    'uc0': {
                        'ansible_host': 'x.x.x.1',
                        'canonical_hostname': 'uc0.lab.example.com',
                        'ctlplane_hostname': 'uc0.ctlplane.localdomain',
                        'ctlplane_ip': 'x.x.x.1',
                        'deploy_server_id': 'a',
                        'external_hostname': 'uc0.external.localdomain',
                        'external_ip': 'x.x.x.1'}},
                'vars': {
                    'ansible_ssh_user': 'heat-admin',
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'Undercloud',
                    'tripleo_role_networks': ['ctlplane', 'external']}},
            'allovercloud': {
                'children': {'Undercloud': {}},
                'vars': {'container_cli': 'podman',
                         'ctlplane_vip': 'x.x.x.4',
                         'redis_vip': 'x.x.x.6'}},
            'sb': {'children': {'Undercloud': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'sa': {'children': {'Undercloud': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}}
            }
        inv_list = inventory.list(dynamic=False)
        for k in expected:
            self.assertEqual(expected[k], inv_list[k])

    def test_inventory_list_undercloud_only(self):
        self.inventory.plan_name = None
        self.inventory.undercloud_connection = 'local'
        expected = {
            'Undercloud': {
                'hosts': ['undercloud'],
                'vars': {
                    'ansible_connection': 'local',
                    'ansible_host': 'localhost',
                    'ansible_python_interpreter': sys.executable,
                    'ansible_remote_tmp': '/tmp/ansible-${USER}',
                    'undercloud_service_list': [
                        'tripleo_nova_compute',
                        'tripleo_heat_engine',
                        'tripleo_ironic_conductor',
                        'tripleo_swift_container_server',
                        'tripleo_swift_object_server',
                        'tripleo_mistral_engine'
                        ],
                }
            },
            '_meta': {'hostvars': {}},
        }
        self.assertEqual(expected, self.inventory.list())

    def test_ansible_ssh_user(self):
        self._try_alternative_args(
            ansible_ssh_user='my-custom-admin', undercloud_connection='ssh')

    def _try_alternative_args(self, ansible_ssh_user, undercloud_connection):
        key_file = '/var/lib/mistral/.ssh/%s-key' % ansible_ssh_user
        self.inventory = TripleoInventory(
            hclient=self.hclient,
            cloud_name='undercloud',
            plan_name=self.plan_name,
            ansible_ssh_user=ansible_ssh_user,
            undercloud_connection=undercloud_connection,
            undercloud_key_file=key_file,
            ansible_python_interpreter='foo'
        )

        self.inventory.stack_outputs = self.outputs

        expected = {
            'Compute': {
                'hosts': ['cp-0'],
                'vars': {
                    'ansible_python_interpreter': 'foo',
                    'ansible_ssh_user': ansible_ssh_user,
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'Compute',
                    'tripleo_role_networks': ['ctlplane']
                    }
                },
            'Controller': {
                'hosts': ['c-0', 'c-1', 'c-2'],
                'vars': {
                    'ansible_python_interpreter': 'foo',
                    'ansible_ssh_user': ansible_ssh_user,
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'Controller',
                    'tripleo_role_networks': [
                        'ctlplane',
                        'internal_api'
                        ]
                    }
                },
            'CustomRole': {
                'hosts': ['cs-0'],
                'vars': {
                    'ansible_python_interpreter': 'foo',
                    'ansible_ssh_user': ansible_ssh_user,
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'CustomRole',
                    'tripleo_role_networks': ['ctlplane']
                    }
            },
            'overcloud': {
                'children': ['allovercloud']
            },
            'allovercloud': {
                'children': ['Compute', 'Controller', 'CustomRole'],
                'vars': {
                    'container_cli': 'podman',
                    'ctlplane_vip': 'x.x.x.4',
                    'redis_vip': 'x.x.x.6'
                }
            },
            'sa': {
                'children': ['Controller'],
                'vars': {
                    'ansible_ssh_user': 'my-custom-admin',
                    'ansible_python_interpreter': 'foo'
                }
            },
            'sb': {
                'children': ['Controller'],
                'vars': {
                    'ansible_ssh_user': 'my-custom-admin',
                    'ansible_python_interpreter': 'foo'
                }
            },
            'sd': {
                'children': ['Compute'],
                'vars': {
                    'ansible_ssh_user': 'my-custom-admin',
                    'ansible_python_interpreter': 'foo'
                }
            },
            'se': {
                'children': ['Compute'],
                'vars': {
                    'ansible_ssh_user': 'my-custom-admin',
                    'ansible_python_interpreter': 'foo'
                }
            },
            'ceph_client': {
                'children': ['Compute'],
                'vars': {
                    'ansible_ssh_user': 'my-custom-admin',
                    'ansible_python_interpreter': 'foo'
                }
            },
            'clients': {
                'children': ['Compute'],
                'vars': {
                    'ansible_ssh_user': 'my-custom-admin',
                    'ansible_python_interpreter': 'foo'
                    }
                },
            'sg': {
                'children': ['CustomRole'],
                'vars': {
                    'ansible_ssh_user': 'my-custom-admin',
                    'ansible_python_interpreter': 'foo'
                }
            },
            'sh': {
                'children': ['CustomRole'],
                'vars': {
                    'ansible_ssh_user': 'my-custom-admin',
                    'ansible_python_interpreter': 'foo'
                    }
                },
            'Undercloud': {
                'hosts': ['undercloud'],
                'vars': {
                    'ansible_connection': 'ssh',
                    'ansible_ssh_private_key_file': key_file,
                    'ansible_ssh_user': 'my-custom-admin',
                    'ansible_host': 'localhost',
                    'ansible_python_interpreter': 'foo',
                    'ansible_remote_tmp': '/tmp/ansible-${USER}',
                    'overcloud_keystone_url': 'xyz://keystone',
                    'overcloud_admin_password': 'theadminpw',
                    'plan': 'overcloud',
                    'undercloud_service_list': [
                        'tripleo_nova_compute',
                        'tripleo_heat_engine',
                        'tripleo_ironic_conductor',
                        'tripleo_swift_container_server',
                        'tripleo_swift_object_server',
                        'tripleo_mistral_engine'],
                    }
                }
            }

        inv_list = self.inventory.list()
        for k in expected:
            self.assertEqual(expected[k], inv_list[k])

    def test_inventory_write_static(self):
        self.inventory.undercloud_connection = 'local'
        self._inventory_write_static()

    def test_inventory_write_static_extra_vars(self):
        self.inventory.undercloud_connection = 'local'
        extra_vars = {'Undercloud': {'anextravar': 123}}
        self._inventory_write_static(extra_vars=extra_vars)

    def _inventory_write_static(self, extra_vars=None):
        tmp_dir = self.useFixture(fixtures.TempDir()).path
        inv_path = os.path.join(tmp_dir, "inventory.yaml")
        self.inventory.write_static_inventory(inv_path, extra_vars)
        ansible_ssh_user = 'heat-admin'
        expected = {
            'Undercloud': {
                'hosts': {'undercloud': {}},
                'vars': {
                    'ansible_connection': 'local',
                    'ansible_host': 'localhost',
                    'ansible_python_interpreter':
                    sys.executable,
                    'ansible_remote_tmp':
                    '/tmp/ansible-${USER}',
                    'overcloud_admin_password': 'theadminpw',
                    'overcloud_keystone_url': 'xyz://keystone',
                    'plan': 'overcloud',
                    'undercloud_service_list': [
                        'tripleo_nova_compute',
                        'tripleo_heat_engine',
                        'tripleo_ironic_conductor',
                        'tripleo_swift_container_server',
                        'tripleo_swift_object_server',
                        'tripleo_mistral_engine'],
                }
            },
            'Controller': {
                'hosts': {
                    'c-0': {
                        'ansible_host': 'x.x.x.1',
                        'ctlplane_ip': 'x.x.x.1',
                        'deploy_server_id': 'a',
                        'ctlplane_hostname': 'c-0.ctlplane.localdomain',
                        'internal_api_hostname':
                        'c-0.internal_api.localdomain',
                        'internal_api_ip': 'x.x.x.4'
                    },
                    'c-1': {
                        'ansible_host': 'x.x.x.2',
                        'ctlplane_ip': 'x.x.x.2',
                        'deploy_server_id': 'b',
                        'ctlplane_hostname': 'c-1.ctlplane.localdomain',
                        'internal_api_hostname':
                        'c-1.internal_api.localdomain',
                        'internal_api_ip': 'x.x.x.5'
                    },
                    'c-2': {
                        'ansible_host': 'x.x.x.3',
                        'ctlplane_ip': 'x.x.x.3',
                        'deploy_server_id': 'c',
                        'ctlplane_hostname': 'c-2.ctlplane.localdomain',
                        'internal_api_hostname':
                        'c-2.internal_api.localdomain',
                        'internal_api_ip': 'x.x.x.6'
                    }
                },
                'vars': {
                    'ansible_ssh_user': ansible_ssh_user,
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'Controller',
                    'tripleo_role_networks': [
                        'ctlplane',
                        'internal_api'
                    ]
                }
            },
            'Compute': {
                'hosts': {
                    'cp-0': {
                        'ansible_host': 'y.y.y.1',
                        'ctlplane_ip': 'y.y.y.1',
                        'deploy_server_id': 'd',
                        'ctlplane_hostname': 'cp-0.ctlplane.localdomain'
                    }
                },
                'vars': {
                    'ansible_ssh_user': ansible_ssh_user,
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'Compute',
                    'tripleo_role_networks': ['ctlplane']
                }
            },
            'CustomRole': {
                'hosts': {
                    'cs-0': {
                        'ansible_host': 'z.z.z.1',
                        'ctlplane_ip': 'z.z.z.1',
                        'deploy_server_id': 'e',
                        'ctlplane_hostname': 'cs-0.ctlplane.localdomain'
                    }
                },
                'vars': {
                    'ansible_ssh_user': ansible_ssh_user,
                    'bootstrap_server_id': 'a',
                    'serial': 1,
                    'tripleo_role_name': 'CustomRole',
                    'tripleo_role_networks': ['ctlplane']
                }
            },
            'overcloud': {
                'children': {'allovercloud': {}}
            },
            'allovercloud': {
                'children': {
                    'Compute': {},
                    'Controller': {},
                    'CustomRole': {}
                },
                'vars': {
                    'container_cli': 'podman',
                    'ctlplane_vip': 'x.x.x.4',
                    'redis_vip': 'x.x.x.6'
                }
            },
            'sa': {
                'children': {'Controller': {}},
                'vars': {'ansible_ssh_user': 'heat-admin'}
            },
            'sb': {
                'children': {'Controller': {}},
                'vars': {'ansible_ssh_user': 'heat-admin'}
            },
            'sd': {
                'children': {'Compute': {}},
                'vars': {'ansible_ssh_user': 'heat-admin'}
            },
            'se': {
                'children': {'Compute': {}},
                'vars': {'ansible_ssh_user': 'heat-admin'}
            },
            'ceph_client': {
                'children': {'Compute': {}},
                'vars': {'ansible_ssh_user': 'heat-admin'}
            },
            'clients': {
                'children': {'Compute': {}},
                'vars': {'ansible_ssh_user': 'heat-admin'}
            },
            'sg': {
                'children': {'CustomRole': {}},
                'vars': {'ansible_ssh_user': 'heat-admin'}
            },
            'sh': {
                'children': {'CustomRole': {}},
                'vars': {'ansible_ssh_user': 'heat-admin'}
            },
        }
        if extra_vars:
            expected['Undercloud']['vars']['anextravar'] = 123

        with open(inv_path, 'r') as f:
            loaded_inv = yaml.safe_load(f)
        self.assertEqual(expected, loaded_inv)

    def test__add_host_from_neutron_data(self):
        neutron_data = NeutronData(networks=neutron_fakes.fake_networks,
                                   subnets=neutron_fakes.fake_subnets,
                                   ports=neutron_fakes.compute_0_ports)
        ret = OrderedDict()
        role = ret.setdefault('Compute', {})
        role_vars = role.setdefault('vars', {})
        role_networks = role_vars.setdefault('tripleo_role_networks', [])
        hosts = role.setdefault('hosts', {})
        ports = neutron_data.ports_by_role_and_host['Compute']['cp-0']
        self.inventory._add_host_from_neutron_data(hosts, ports, role_networks,
                                                   role_vars)
        self.assertEqual(OrderedDict([
            ('Compute',
             {'hosts': {
                 'ansible_host': '192.0.2.20',
                 'canonical_hostname': 'cp-0.example.com',
                 'ctlplane_hostname': 'cp-0.ctlplane.example.com',
                 'ctlplane_ip': '192.0.2.20',
                 'internal_api_hostname': 'cp-0.internalapi.example.com',
                 'internal_api_ip': '198.51.100.150'},
                 'vars': {
                     'ctlplane_cidr': '24',
                     'ctlplane_dns_nameservers': ['192.0.2.253',
                                                  '192.0.2.254'],
                     'ctlplane_gateway_ip': '192.0.2.1',
                     'ctlplane_host_routes': [{'default': True,
                                               'nexthop': '192.0.2.1'}],
                     'ctlplane_vlan_id': '1',
                     'internal_api_cidr': '25',
                     'internal_api_dns_nameservers': [],
                     'internal_api_gateway_ip': '198.51.100.129',
                     'internal_api_host_routes': [],
                     'internal_api_vlan_id': '20',
                     'tripleo_role_networks': ['ctlplane', 'internal_api']
                 }})
        ]), ret)

    def test__inventory_from_neutron_data(self):
        ret = OrderedDict()
        children = set()
        fake_ports = (neutron_fakes.controller0_ports +
                      neutron_fakes.controller1_ports +
                      neutron_fakes.compute_0_ports)
        self.inventory.neutron_data = NeutronData(
            networks=neutron_fakes.fake_networks,
            subnets=neutron_fakes.fake_subnets,
            ports=fake_ports)

        self.inventory._inventory_from_neutron_data(ret, children, False)
        self.assertEqual({'Compute', 'Controller'}, children)
        self.assertEqual(OrderedDict([
            ('Controller',
             {'hosts': {
                 'c-0': {
                     'ansible_host': '192.0.2.10',
                     'canonical_hostname': 'c-0.example.com',
                     'ctlplane_hostname': 'c-0.ctlplane.example.com',
                     'ctlplane_ip': '192.0.2.10',
                     'internal_api_hostname': 'c-0.internalapi.example.com',
                     'internal_api_ip': '198.51.100.140'},
                 'c-1': {
                     'ansible_host': '192.0.2.11',
                     'canonical_hostname': 'c-1.example.com',
                     'ctlplane_hostname': 'c-1.ctlplane.example.com',
                     'ctlplane_ip': '192.0.2.11',
                     'internal_api_hostname': 'c-1.internalapi.example.com',
                     'internal_api_ip': '198.51.100.141'}},
                 'vars': {'ansible_ssh_user': 'heat-admin',
                          'ctlplane_cidr': '24',
                          'ctlplane_dns_nameservers': ['192.0.2.253',
                                                       '192.0.2.254'],
                          'ctlplane_gateway_ip': '192.0.2.1',
                          'ctlplane_host_routes': [{'default': True,
                                                    'nexthop': '192.0.2.1'}],
                          'ctlplane_mtu': 1500,
                          'ctlplane_subnet_cidr': '24',
                          'ctlplane_vlan_id': '1',
                          'internal_api_cidr': '25',
                          'internal_api_dns_nameservers': [],
                          'internal_api_gateway_ip': '198.51.100.129',
                          'internal_api_host_routes': [],
                          'internal_api_mtu': 1500,
                          'internal_api_vlan_id': '20',
                          'networks_all': ['InternalApi'],
                          'networks_lower': {'InternalApi': 'internal_api',
                                             'ctlplane': 'ctlplane'},
                          'role_networks': ['ctlplane', 'InternalApi'],
                          'serial': 1,
                          'tripleo_role_name': 'Controller',
                          'tripleo_role_networks': ['ctlplane', 'internal_api']
                          }}),
            ('Compute',
             {'hosts': {
                 'cp-0': {
                     'ansible_host': '192.0.2.20',
                     'canonical_hostname': 'cp-0.example.com',
                     'ctlplane_hostname': 'cp-0.ctlplane.example.com',
                     'ctlplane_ip': '192.0.2.20',
                     'internal_api_hostname': 'cp-0.internalapi.example.com',
                     'internal_api_ip': '198.51.100.150'}},
                 'vars': {'ansible_ssh_user': 'heat-admin',
                          'ctlplane_cidr': '24',
                          'ctlplane_dns_nameservers': ['192.0.2.253',
                                                       '192.0.2.254'],
                          'ctlplane_gateway_ip': '192.0.2.1',
                          'ctlplane_host_routes': [{'default': True,
                                                    'nexthop': '192.0.2.1'}],
                          'ctlplane_mtu': 1500,
                          'ctlplane_subnet_cidr': '24',
                          'ctlplane_vlan_id': '1',
                          'internal_api_cidr': '25',
                          'internal_api_dns_nameservers': [],
                          'internal_api_gateway_ip': '198.51.100.129',
                          'internal_api_host_routes': [],
                          'internal_api_mtu': 1500,
                          'internal_api_vlan_id': '20',
                          'networks_all': ['InternalApi'],
                          'networks_lower': {'InternalApi': 'internal_api',
                                             'ctlplane': 'ctlplane'},
                          'role_networks': ['ctlplane', 'InternalApi'],
                          'serial': 1,
                          'tripleo_role_name': 'Compute',
                          'tripleo_role_networks': ['ctlplane', 'internal_api']
                          }}),
            ('allovercloud', {'children': {'Compute': {}, 'Controller': {}}})
        ]), ret)

    def test__inventory_from_neutron_data_dynamic(self):
        ret = OrderedDict()
        children = set()
        fake_ports = (neutron_fakes.controller0_ports +
                      neutron_fakes.controller1_ports +
                      neutron_fakes.compute_0_ports)
        self.inventory.neutron_data = NeutronData(
            networks=neutron_fakes.fake_networks,
            subnets=neutron_fakes.fake_subnets,
            ports=fake_ports)

        self.inventory._inventory_from_neutron_data(ret, children, True)
        self.assertEqual({'Compute', 'Controller'}, children)
        self.assertEqual(OrderedDict([
            ('Controller', {
                'hosts': ['c-0', 'c-1'],
                'vars': {'ansible_ssh_user': 'heat-admin',
                         'ctlplane_cidr': '24',
                         'ctlplane_dns_nameservers': ['192.0.2.253',
                                                      '192.0.2.254'],
                         'ctlplane_gateway_ip': '192.0.2.1',
                         'ctlplane_host_routes': [{'default': True,
                                                   'nexthop': '192.0.2.1'}],
                         'ctlplane_mtu': 1500,
                         'ctlplane_vlan_id': '1',
                         'internal_api_cidr': '25',
                         'internal_api_dns_nameservers': [],
                         'internal_api_gateway_ip': '198.51.100.129',
                         'internal_api_host_routes': [],
                         'internal_api_mtu': 1500,
                         'ctlplane_subnet_cidr': '24',
                         'internal_api_vlan_id': '20',
                         'networks_all': ['InternalApi'],
                         'networks_lower': {'InternalApi': 'internal_api',
                                            'ctlplane': 'ctlplane'},
                         'role_networks': ['ctlplane', 'InternalApi'],
                         'serial': 1,
                         'tripleo_role_name': 'Controller',
                         'tripleo_role_networks': ['ctlplane', 'internal_api']
                         }}),
            ('Compute', {
                'hosts': ['cp-0'],
                'vars': {'ansible_ssh_user': 'heat-admin',
                         'ctlplane_cidr': '24',
                         'ctlplane_dns_nameservers': ['192.0.2.253',
                                                      '192.0.2.254'],
                         'ctlplane_gateway_ip': '192.0.2.1',
                         'ctlplane_host_routes': [{'default': True,
                                                   'nexthop': '192.0.2.1'}],
                         'ctlplane_mtu': 1500,
                         'ctlplane_vlan_id': '1',
                         'internal_api_cidr': '25',
                         'internal_api_dns_nameservers': [],
                         'internal_api_gateway_ip': '198.51.100.129',
                         'internal_api_host_routes': [],
                         'internal_api_mtu': 1500,
                         'ctlplane_subnet_cidr': '24',
                         'internal_api_vlan_id': '20',
                         'networks_all': ['InternalApi'],
                         'networks_lower': {'InternalApi': 'internal_api',
                                            'ctlplane': 'ctlplane'},
                         'role_networks': ['ctlplane', 'InternalApi'],
                         'serial': 1,
                         'tripleo_role_name': 'Compute',
                         'tripleo_role_networks': ['ctlplane', 'internal_api']
                         }}),
            ('allovercloud', {'children': ['Compute', 'Controller']})]
        ), ret)

    @mock.patch.object(TripleoInventory, '_get_neutron_data', autospec=True)
    def test_inventory_list_with_neutron_and_heat(self, mock_get_neutron_data):
        fake_ports = (neutron_fakes.controller0_ports +
                      neutron_fakes.controller1_ports +
                      neutron_fakes.controller2_ports +
                      neutron_fakes.compute_0_ports +
                      neutron_fakes.custom_0_ports)
        mock_get_neutron_data.return_value = NeutronData(
            networks=neutron_fakes.fake_networks,
            subnets=neutron_fakes.fake_subnets,
            ports=fake_ports)
        inv_list = self.inventory.list(dynamic=False)
        c_0 = inv_list['Controller']['hosts']['c-0']
        c_1 = inv_list['Controller']['hosts']['c-1']
        c_2 = inv_list['Controller']['hosts']['c-2']
        cp_0 = inv_list['Compute']['hosts']['cp-0']
        cs_0 = inv_list['CustomRole']['hosts']['cs-0']

        # The setdefault pattern should always put the value discovered first
        # in the inventory, neutron source run's prior to heat stack source.
        # Assert IP addresses from neutron fake are used in the
        # inventory, not the heat stack IPs.

        # Controller
        self.assertNotEqual(
            c_0['ctlplane_ip'],
            self.outputs['RoleNetIpMap']['Controller']['ctlplane'][0])
        self.assertNotEqual(
            c_0['ansible_host'],
            self.outputs['RoleNetIpMap']['Controller']['ctlplane'][0])
        self.assertNotEqual(
            c_1['ctlplane_ip'],
            self.outputs['RoleNetIpMap']['Controller']['ctlplane'][1])
        self.assertNotEqual(
            c_1['ansible_host'],
            self.outputs['RoleNetIpMap']['Controller']['ctlplane'][1])
        self.assertNotEqual(
            c_2['ctlplane_ip'],
            self.outputs['RoleNetIpMap']['Controller']['ctlplane'][2])
        self.assertNotEqual(
            c_2['ansible_host'],
            self.outputs['RoleNetIpMap']['Controller']['ctlplane'][2])
        # Compute
        self.assertNotEqual(
            cp_0['ctlplane_ip'],
            self.outputs['RoleNetIpMap']['Compute']['ctlplane'][0])
        self.assertNotEqual(
            cp_0['ansible_host'],
            self.outputs['RoleNetIpMap']['Compute']['ctlplane'][0])
        # CustomRole
        self.assertNotEqual(
            cs_0['ctlplane_ip'],
            self.outputs['RoleNetIpMap']['CustomRole']['ctlplane'][0])
        self.assertNotEqual(
            cs_0['ansible_host'],
            self.outputs['RoleNetIpMap']['CustomRole']['ctlplane'][0])

        # IP's and hostnames are from neutron while deploy_server_id and
        # bootstrap_server_id, serial etc are from heat.
        expected = {
            'Undercloud': {
                'hosts': {'undercloud': {}},
                'vars': {'ansible_connection': 'local',
                         'ansible_host': 'localhost',
                         'ansible_python_interpreter': sys.executable,
                         'ansible_remote_tmp': '/tmp/ansible-${USER}',
                         'overcloud_admin_password': 'theadminpw',
                         'overcloud_keystone_url': 'xyz://keystone',
                         'plan': 'overcloud',
                         'undercloud_service_list': [
                             'tripleo_nova_compute',
                             'tripleo_heat_engine',
                             'tripleo_ironic_conductor',
                             'tripleo_swift_container_server',
                             'tripleo_swift_object_server',
                             'tripleo_mistral_engine']}},
            'Controller': {
                'hosts': {
                    'c-0': {
                        'ansible_host': '192.0.2.10',
                        'canonical_hostname': 'c-0.example.com',
                        'ctlplane_hostname': 'c-0.ctlplane.example.com',
                        'ctlplane_ip': '192.0.2.10',
                        'deploy_server_id': 'a',
                        'internal_api_hostname': 'c-0.internalapi.example.com',
                        'internal_api_ip': '198.51.100.140'},
                    'c-1': {
                        'ansible_host': '192.0.2.11',
                        'canonical_hostname': 'c-1.example.com',
                        'ctlplane_hostname': 'c-1.ctlplane.example.com',
                        'ctlplane_ip': '192.0.2.11',
                        'deploy_server_id': 'b',
                        'internal_api_hostname': 'c-1.internalapi.example.com',
                        'internal_api_ip': '198.51.100.141'},
                    'c-2': {
                        'ansible_host': '192.0.2.12',
                        'canonical_hostname': 'c-2.example.com',
                        'ctlplane_hostname': 'c-2.ctlplane.example.com',
                        'ctlplane_ip': '192.0.2.12',
                        'deploy_server_id': 'c',
                        'internal_api_hostname': 'c-2.internalapi.example.com',
                        'internal_api_ip': '198.51.100.142'}},
                'vars': {
                    'ansible_ssh_user': 'heat-admin',
                    'bootstrap_server_id': 'a',
                    'ctlplane_cidr': '24',
                    'ctlplane_dns_nameservers': ['192.0.2.253', '192.0.2.254'],
                    'ctlplane_gateway_ip': '192.0.2.1',
                    'ctlplane_host_routes': [{'default': True,
                                              'nexthop': '192.0.2.1'}],
                    'ctlplane_mtu': 1500,
                    'ctlplane_subnet_cidr': '24',
                    'ctlplane_vlan_id': '1',
                    'internal_api_cidr': '25',
                    'internal_api_dns_nameservers': [],
                    'internal_api_gateway_ip': '198.51.100.129',
                    'internal_api_host_routes': [],
                    'internal_api_mtu': 1500,
                    'internal_api_vlan_id': '20',
                    'networks_all': ['InternalApi'],
                    'networks_lower': {'InternalApi': 'internal_api',
                                       'ctlplane': 'ctlplane'},
                    'role_networks': ['ctlplane', 'InternalApi'],
                    'serial': 1,
                    'tripleo_role_name': 'Controller',
                    'tripleo_role_networks': ['ctlplane', 'internal_api']}
            },
            'Compute': {
                'hosts': {
                    'cp-0': {
                        'ansible_host': '192.0.2.20',
                        'canonical_hostname': 'cp-0.example.com',
                        'ctlplane_hostname': 'cp-0.ctlplane.example.com',
                        'ctlplane_ip': '192.0.2.20',
                        'deploy_server_id': 'd',
                        'internal_api_hostname':
                            'cp-0.internalapi.example.com',
                        'internal_api_ip': '198.51.100.150'}},
                'vars': {'ansible_ssh_user': 'heat-admin',
                         'bootstrap_server_id': 'a',
                         'ctlplane_cidr': '24',
                         'ctlplane_dns_nameservers': ['192.0.2.253',
                                                      '192.0.2.254'],
                         'ctlplane_gateway_ip': '192.0.2.1',
                         'ctlplane_host_routes': [{'default': True,
                                                   'nexthop': '192.0.2.1'}],
                         'ctlplane_mtu': 1500,
                         'ctlplane_subnet_cidr': '24',
                         'ctlplane_vlan_id': '1',
                         'internal_api_cidr': '25',
                         'internal_api_dns_nameservers': [],
                         'internal_api_gateway_ip': '198.51.100.129',
                         'internal_api_host_routes': [],
                         'internal_api_mtu': 1500,
                         'internal_api_vlan_id': '20',
                         'networks_all': ['InternalApi'],
                         'networks_lower': {'InternalApi': 'internal_api',
                                            'ctlplane': 'ctlplane'},
                         'role_networks': ['ctlplane', 'InternalApi'],
                         'serial': 1,
                         'tripleo_role_name': 'Compute',
                         'tripleo_role_networks': ['ctlplane', 'internal_api']}
            },
            'CustomRole': {
                'hosts': {
                    'cs-0': {
                        'ansible_host': '192.0.2.200',
                        'canonical_hostname': 'cs-0.example.com',
                        'ctlplane_hostname': 'cs-0.ctlplane.example.com',
                        'ctlplane_ip': '192.0.2.200',
                        'deploy_server_id': 'e'}},
                'vars': {'ansible_ssh_user': 'heat-admin',
                         'bootstrap_server_id': 'a',
                         'ctlplane_cidr': '24',
                         'ctlplane_dns_nameservers': ['192.0.2.253',
                                                      '192.0.2.254'],
                         'ctlplane_gateway_ip': '192.0.2.1',
                         'ctlplane_host_routes': [{'default': True,
                                                   'nexthop': '192.0.2.1'}],
                         'ctlplane_mtu': 1500,
                         'ctlplane_subnet_cidr': '24',
                         'ctlplane_vlan_id': '1',
                         'internal_api_mtu': 1500,
                         'networks_all': ['InternalApi'],
                         'networks_lower': {'InternalApi': 'internal_api',
                                            'ctlplane': 'ctlplane'},
                         'role_networks': ['ctlplane'],
                         'serial': 1,
                         'tripleo_role_name': 'CustomRole',
                         'tripleo_role_networks': ['ctlplane']}
            },
            'allovercloud': {
                'children': {'Compute': {},
                             'Controller': {},
                             'CustomRole': {}},
                'vars': {'container_cli': 'podman',
                         'ctlplane_vip': 'x.x.x.4',
                         'redis_vip': 'x.x.x.6'}
            },
            'overcloud': {'children': {'allovercloud': {}}},
            'sa': {'children': {'Controller': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'se': {'children': {'Compute': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'sd': {'children': {'Compute': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'sb': {'children': {'Controller': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'sg': {'children': {'CustomRole': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'ceph_client': {'children': {'Compute': {}},
                            'vars': {'ansible_ssh_user': 'heat-admin'}},
            'sh': {'children': {'CustomRole': {}},
                   'vars': {'ansible_ssh_user': 'heat-admin'}},
            'clients': {'children': {'Compute': {}},
                        'vars': {'ansible_ssh_user': 'heat-admin'}},
        }
        for k in expected:
            self.assertEqual(expected[k], inv_list[k])

    def test__extend_inventory(self):
        dynamic = False
        existing_inventory = OrderedDict()
        existing_inventory.update({
            'RoleA': {
                'hosts': {
                    'host0': {
                        'existing': 'existing_value'
                    }
                },
                'vars': {
                    'existing': 'existing_value'
                },
            }
        })
        extend_data = {
            'RoleA': {
                'hosts': {
                    'host0': {
                        'new': 'new_value',
                        'existing': 'not_overwritten',
                    }
                },
                'vars': {
                    'new': 'new_var_is_added',
                    'existing': 'not_overwritten',
                },
            }
        }
        expected_inventory = OrderedDict([(
            'RoleA', {
                'hosts': {
                    'host0': {
                        'existing': 'existing_value',
                        'new': 'new_value'
                    }
                },
                'vars': {
                    'existing': 'existing_value',
                    'new': 'new_var_is_added'
                }
            }
        )])

        self.inventory._extend_inventory(existing_inventory, dynamic,
                                         data=extend_data)
        self.assertEqual(expected_inventory, existing_inventory)

    def test__extend_inventory_dynamic(self):
        dynamic = True
        existing_inventory = OrderedDict()
        existing_inventory.update({
            'RoleA': {
                'hosts': {
                    'host0': {
                        'existing': 'existing_value'
                    }
                },
                'vars': {
                    'existing': 'existing_value'
                },
            }
        })
        extend_data = {
            'RoleA': {
                'hosts': {
                    'host0': {
                        'new': 'new_value',
                        'existing': 'not_overwritten',
                    }
                },
                'vars': {
                    'new': 'new_var_is_added',
                    'existing': 'not_overwritten',
                },
            }
        }
        expected_inventory = OrderedDict([(
            'RoleA', {
                'hosts': ['host0'],
                'vars':
                    {'existing': 'existing_value',
                     'new': 'new_var_is_added'}})])

        self.inventory._extend_inventory(existing_inventory, dynamic,
                                         data=extend_data)
        self.assertEqual(expected_inventory, existing_inventory)
        self.assertEqual(
            {'host0': {'existing': 'existing_value',
                       'new': 'new_value'}}, self.inventory.hostvars)


class TestNeutronData(base.TestCase):
    def setUp(self):
        super(TestNeutronData, self).setUp()
        fake_ports = (neutron_fakes.controller0_ports +
                      neutron_fakes.controller1_ports +
                      neutron_fakes.compute_0_ports)
        self.neutron_data = NeutronData(networks=neutron_fakes.fake_networks,
                                        subnets=neutron_fakes.fake_subnets,
                                        ports=fake_ports)

    def test__tags_to_dict(self):
        tags = ['tripleo_foo=foo', 'tripleo_bar=bar', 'other_tag']
        self.assertEqual({'tripleo_foo': 'foo', 'tripleo_bar': 'bar'},
                         NeutronData._tags_to_dict(self, tags))

    def test__networks_by_id(self):
        self.assertEqual({
            'ctlplane_network_id': {
                'dns_domain': 'ctlplane.example.com.',
                'mtu': 1500,
                'name': 'ctlplane',
                'name_upper': 'ctlplane',
                'subnet_ids': ['ctlplane_subnet_id'],
                'tags': {}},
            'internal_api_network_id': {
                'dns_domain': 'internalapi.example.com.',
                'mtu': 1500,
                'name': 'internal_api',
                'name_upper': 'InternalApi',
                'subnet_ids': ['internal_api_subnet_id'],
                'tags': {'tripleo_net_idx': 0,
                         'tripleo_network_name': 'InternalApi',
                         'tripleo_vip': True}
            },
        }, self.neutron_data.networks_by_id)

    def test__subnets_by_id(self):
        self.assertEqual({
            'ctlplane_subnet_id': {
                'cidr': '192.0.2.0/24',
                'dns_nameservers': ['192.0.2.253', '192.0.2.254'],
                'gateway_ip': '192.0.2.1',
                'host_routes': [],
                'ip_version': 4,
                'name': 'ctlplane-subnet',
                'network_id': 'ctlplane_network_id',
                'tags': {}
            },
            'internal_api_subnet_id': {
                'cidr': '198.51.100.128/25',
                'dns_nameservers': [],
                'gateway_ip': '198.51.100.129',
                'host_routes': [],
                'ip_version': 4,
                'name': 'internal_api_subnet',
                'network_id': 'internal_api_network_id',
                'tags': {'tripleo_vlan_id': '20'}
            },
        }, self.neutron_data.subnets_by_id)

    def test__ports_by_role_and_host(self):
        self.assertTrue(
            'Controller' in self.neutron_data.ports_by_role_and_host)
        self.assertTrue(
            'Compute' in self.neutron_data.ports_by_role_and_host)
        ctr_role = self.neutron_data.ports_by_role_and_host['Controller']
        cmp_role = self.neutron_data.ports_by_role_and_host['Compute']
        self.assertTrue('c-0' in ctr_role)
        self.assertTrue('c-1' in ctr_role)
        ctr_0 = ctr_role['c-0']
        ctr_1 = ctr_role['c-1']
        self.assertTrue('cp-0' in cmp_role)
        cmp_0 = cmp_role['cp-0']
        self.assertEqual(
            [{'cidr': '24',
              'dns_domain': 'ctlplane.example.com',
              'dns_nameservers': ['192.0.2.253', '192.0.2.254'],
              'fixed_ips': [{'ip_address': '192.0.2.10',
                             'subnet_id': 'ctlplane_subnet_id'}],
              'gateway_ip': '192.0.2.1',
              'host_routes': [{'default': True, 'nexthop': '192.0.2.1'}],
              'hostname': 'c-0',
              'ip_address': '192.0.2.10',
              'mtu': 1500,
              'name': 'c-0-ctlplane',
              'network_id': 'ctlplane_network_id',
              'network_name': 'ctlplane',
              'subnet_id': 'ctlplane_subnet_id',
              'tags': {'tripleo_default_route': True,
                       'tripleo_network_name': 'ctlplane',
                       'tripleo_role': 'Controller',
                       'tripleo_stack': 'overcloud'},
              'vlan_id': '1'},
             {'cidr': '25',
              'dns_domain': 'internalapi.example.com',
              'dns_nameservers': [],
              'fixed_ips': [{'ip_address': '198.51.100.140',
                             'subnet_id': 'internal_api_subnet_id'}],
              'gateway_ip': '198.51.100.129',
              'host_routes': [],
              'hostname': 'c-0',
              'ip_address': '198.51.100.140',
              'mtu': 1500,
              'name': 'c-0-internal_api',
              'network_id': 'internal_api_network_id',
              'network_name': 'internal_api',
              'subnet_id': 'internal_api_subnet_id',
              'tags': {'tripleo_default_route': False,
                       'tripleo_network_name': 'InternalApi',
                       'tripleo_role': 'Controller',
                       'tripleo_stack': 'overcloud'},
              'vlan_id': '20'}],
            ctr_0
        )
        self.assertEqual(
            [{'cidr': '24',
              'dns_domain': 'ctlplane.example.com',
              'dns_nameservers': ['192.0.2.253', '192.0.2.254'],
              'fixed_ips': [{'ip_address': '192.0.2.11',
                             'subnet_id': 'ctlplane_subnet_id'}],
              'gateway_ip': '192.0.2.1',
              'host_routes': [{'default': True, 'nexthop': '192.0.2.1'}],
              'hostname': 'c-1',
              'ip_address': '192.0.2.11',
              'mtu': 1500,
              'name': 'c-1-ctlplane',
              'network_id': 'ctlplane_network_id',
              'network_name': 'ctlplane',
              'subnet_id': 'ctlplane_subnet_id',
              'tags': {'tripleo_default_route': True,
                       'tripleo_network_name': 'ctlplane',
                       'tripleo_role': 'Controller',
                       'tripleo_stack': 'overcloud'},
              'vlan_id': '1'},
             {'cidr': '25',
              'dns_domain': 'internalapi.example.com',
              'dns_nameservers': [],
              'fixed_ips': [{'ip_address': '198.51.100.141',
                             'subnet_id': 'internal_api_subnet_id'}],
              'gateway_ip': '198.51.100.129',
              'host_routes': [],
              'hostname': 'c-1',
              'ip_address': '198.51.100.141',
              'mtu': 1500,
              'name': 'c-1-internal_api',
              'network_id': 'internal_api_network_id',
              'network_name': 'internal_api',
              'subnet_id': 'internal_api_subnet_id',
              'tags': {'tripleo_default_route': False,
                       'tripleo_network_name': 'InternalApi',
                       'tripleo_role': 'Controller',
                       'tripleo_stack': 'overcloud'},
              'vlan_id': '20'}],
            ctr_1
        )
        self.assertEqual(
            [{'cidr': '24',
              'dns_domain': 'ctlplane.example.com',
              'dns_nameservers': ['192.0.2.253', '192.0.2.254'],
              'fixed_ips': [{'ip_address': '192.0.2.20',
                             'subnet_id': 'ctlplane_subnet_id'}],
              'gateway_ip': '192.0.2.1',
              'host_routes': [{'default': True, 'nexthop': '192.0.2.1'}],
              'hostname': 'cp-0',
              'ip_address': '192.0.2.20',
              'mtu': 1500,
              'name': 'cp-0-ctlplane',
              'network_id': 'ctlplane_network_id',
              'network_name': 'ctlplane',
              'subnet_id': 'ctlplane_subnet_id',
              'tags': {'tripleo_default_route': True,
                       'tripleo_network_name': 'ctlplane',
                       'tripleo_role': 'Compute',
                       'tripleo_stack': 'overcloud'},
              'vlan_id': '1'},
             {'cidr': '25',
              'dns_domain': 'internalapi.example.com',
              'dns_nameservers': [],
              'fixed_ips': [{'ip_address': '198.51.100.150',
                             'subnet_id': 'internal_api_subnet_id'}],
              'gateway_ip': '198.51.100.129',
              'host_routes': [],
              'hostname': 'cp-0',
              'ip_address': '198.51.100.150',
              'mtu': 1500,
              'name': 'cp-0-internal_api',
              'network_id': 'internal_api_network_id',
              'network_name': 'internal_api',
              'subnet_id': 'internal_api_subnet_id',
              'tags': {'tripleo_default_route': False,
                       'tripleo_network_name': 'InternalApi',
                       'tripleo_role': 'Compute',
                       'tripleo_stack': 'overcloud'},
              'vlan_id': '20'}],
            cmp_0
        )
        self.assertEqual({'Controller': ctr_role, 'Compute': cmp_role},
                         self.neutron_data.ports_by_role_and_host)
