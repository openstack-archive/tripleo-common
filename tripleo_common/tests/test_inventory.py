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
import sys
from unittest.mock import MagicMock

import yaml

from heatclient.exc import HTTPNotFound

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

        self.hclient = MagicMock()
        self.hclient.stacks.environment.return_value = {
            'parameter_defaults': {
                'AdminPassword': 'theadminpw',
                'ContainerCli': 'podman'
                }
            }
        self.mock_stack = MagicMock()
        self.mock_stack.outputs = self.outputs_data['outputs']
        self.hclient.stacks.get.return_value = self.mock_stack

        self.outputs = StackOutputs(self.mock_stack)
        self.inventory = TripleoInventory(
            hclient=self.hclient,
            plan_name=self.plan_name,
            auth_url='xyz://keystone.local',
            cacert='acacert',
            project_name='admin',
            username='admin',
            ansible_ssh_user='heat-admin')
        self.inventory.stack_outputs = self.outputs

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
        self.assertTrue(self.hclient.called_once_with('overcloud',
                                                      'KeystoneURL'))

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
                    'auth_url': 'xyz://keystone.local',
                    'cacert': 'acacert',
                    'overcloud_keystone_url': 'xyz://keystone',
                    'overcloud_admin_password': 'theadminpw',
                    'plan': 'overcloud',
                    'project_name': 'admin',
                    'undercloud_service_list': [
                        'tripleo_nova_compute',
                        'tripleo_heat_engine',
                        'tripleo_ironic_conductor',
                        'tripleo_swift_container_server',
                        'tripleo_swift_object_server',
                        'tripleo_mistral_engine'
                        ],
                    'username': 'admin'
                    }
                }
            }
        inv_list = inventory.list()
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
                    'auth_url': 'xyz://keystone.local',
                    'cacert': 'acacert',
                    'project_name': 'admin',
                    'plan': None,
                    'undercloud_service_list': [
                        'tripleo_nova_compute',
                        'tripleo_heat_engine',
                        'tripleo_ironic_conductor',
                        'tripleo_swift_container_server',
                        'tripleo_swift_object_server',
                        'tripleo_mistral_engine'
                        ],
                    'username': 'admin'
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
            plan_name=self.plan_name,
            auth_url='xyz://keystone.local',
            project_name='admin',
            username='admin',
            cacert='acacert',
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
                    'auth_url': 'xyz://keystone.local',
                    'cacert': 'acacert',
                    'overcloud_keystone_url': 'xyz://keystone',
                    'overcloud_admin_password': 'theadminpw',
                    'plan': 'overcloud',
                    'project_name': 'admin',
                    'undercloud_service_list': [
                        'tripleo_nova_compute',
                        'tripleo_heat_engine',
                        'tripleo_ironic_conductor',
                        'tripleo_swift_container_server',
                        'tripleo_swift_object_server',
                        'tripleo_mistral_engine'],
                    'username': 'admin'
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
                    'auth_url': 'xyz://keystone.local',
                    'cacert': 'acacert',
                    'overcloud_admin_password': 'theadminpw',
                    'overcloud_keystone_url': 'xyz://keystone',
                    'plan': 'overcloud',
                    'project_name': 'admin',
                    'undercloud_service_list': [
                        'tripleo_nova_compute',
                        'tripleo_heat_engine',
                        'tripleo_ironic_conductor',
                        'tripleo_swift_container_server',
                        'tripleo_swift_object_server',
                        'tripleo_mistral_engine'],
                    'username': 'admin'
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
