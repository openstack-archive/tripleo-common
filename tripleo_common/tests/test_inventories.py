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

from mock import MagicMock
from tripleo_common.tests import base
from tripleo_common.inventories import TripleoInventories


class TestInventories(base.TestCase):
    def setUp(self):
        super(TestInventories, self).setUp()
        mock_inv_central = MagicMock()
        mock_inv_edge0 = MagicMock()
        mock_inv_central.list.return_value = self._mock_inv_central_data()
        mock_inv_edge0.list.return_value = self._mock_inv_edge0_data()
        self.stack_to_inv_obj_map = {
            'central': mock_inv_central,
            'edge0': mock_inv_edge0
            }
        self.inventories = TripleoInventories(self.stack_to_inv_obj_map)

    def test_merge(self):
        self.inventories.merge()
        expected = self._mock_inv_merged_data()
        for k in expected.keys():
            self.assertEqual(expected[k], self.inventories.inventory[k])

    def test_inventory_write_static(self):
        self.inventories.merge()
        tmp_dir = self.useFixture(fixtures.TempDir()).path
        inv_path = os.path.join(tmp_dir, "inventory.yaml")
        self.inventories.write_static_inventory(inv_path)
        expected = self._mock_inv_merged_data()
        with open(inv_path, 'r') as f:
            loaded_inv = yaml.safe_load(f)
        self.assertEqual(expected, loaded_inv)

    def _mock_inv_central_data(self):
        return {
            "Undercloud": {
                "hosts": [
                    "undercloud"
                ],
                "vars": {
                    "username": "admin",
                    "overcloud_keystone_url": "http://192.168.24.21:5000",
                    "project_name": "admin",
                    "overcloud_horizon_url": "http://192.168.24.21/dashboard",
                    "auth_url": "https://192.168.24.2:13000",
                    "ansible_connection": "local",
                    "cacert": "/etc/pki/ca-trust/cm-local-ca.pem",
                    "ansible_host": "localhost",
                    "ansible_remote_tmp": "/tmp/ansible-${USER}",
                    "undercloud_service_list": [
                        "tripleo_nova_compute",
                        "tripleo_heat_engine",
                        "tripleo_ironic_conductor",
                        "tripleo_swift_container_server",
                        "tripleo_swift_object_server",
                        "tripleo_mistral_engine"
                    ],
                    "ansible_python_interpreter": "/usr/bin/python",
                    "overcloud_admin_password": "7uCCDn4lIKQ4i7ONsPdgX1KbC",
                    "plan": "central"
                }
            },
            "Controller": {
                "hosts": [
                    "central-controller-0"
                ],
                "vars": {
                    "tripleo_role_name": "Controller",
                    "tripleo_role_networks": [
                        "management",
                        "storage",
                        "ctlplane",
                        "external",
                        "internal_api",
                        "storage_mgmt",
                        "tenant"
                    ],
                    "serial": "1",
                    "ansible_ssh_user": "heat-admin",
                }
            },
            "overcloud": {
                "children": [
                    "Controller"
                ],
                "vars": {
                    "storage_mgmt_vip": "192.168.24.21",
                    "container_cli": "podman",
                    "ctlplane_vip": "192.168.24.21",
                    "redis_vip": "192.168.24.11",
                    "internal_api_vip": "192.168.24.21",
                    "external_vip": "192.168.24.21",
                    "storage_vip": "192.168.24.21"
                }
            },
            "kernel": {
                "children": [
                    "Controller"
                ],
                "vars": {
                    "ansible_ssh_user": "heat-admin"
                }
            },
            "ovn_controller": {
                "children": [
                    "Controller"
                ],
                "vars": {
                    "ansible_ssh_user": "heat-admin"
                }
            },
            "_meta": {
                "hostvars": {
                    "central-controller-0": {
                        "storage_ip": "192.168.24.12",
                        "storage_mgmt_ip": "192.168.24.12",
                        "external_ip": "192.168.24.12",
                        "ctlplane_ip": "192.168.24.12",
                        "tenant_ip": "192.168.24.12",
                        "internal_api_ip": "192.168.24.12",
                        "management_ip": "192.168.24.12",
                        "ansible_host": "192.168.24.12"
                    }
                }
            }
        }

    def _mock_inv_edge0_data(self):
        return {
            "Undercloud": {
                "hosts": [
                    "undercloud"
                ],
                "vars": {
                    "username": "admin",
                    "overcloud_keystone_url": "http://192.168.24.21:5000",
                    "project_name": "admin",
                    "overcloud_horizon_url": "http://192.168.24.21/dashboard",
                    "auth_url": "https://192.168.24.2:13000",
                    "ansible_connection": "local",
                    "cacert": "/etc/pki/ca-trust/cm-local-ca.pem",
                    "ansible_host": "localhost",
                    "ansible_remote_tmp": "/tmp/ansible-${USER}",
                    "undercloud_service_list": [
                        "tripleo_nova_compute",
                        "tripleo_heat_engine",
                        "tripleo_ironic_conductor",
                        "tripleo_swift_container_server",
                        "tripleo_swift_object_server",
                        "tripleo_mistral_engine"
                    ],
                    "ansible_python_interpreter": "/usr/bin/python",
                    "overcloud_admin_password": "7uCCDn4lIKQ4i7ONsPdgX1KbC",
                    "plan": "edge0"
                }
            },
            "DistributedComputeHCI": {
                "hosts": [
                    "edge0-distributedcomputehci-0"
                ],
                "vars": {
                    "tripleo_role_name": "DistributedComputeHCI",
                    "tripleo_role_networks": [
                        "management",
                        "storage",
                        "ctlplane",
                        "external",
                        "internal_api",
                        "storage_mgmt",
                        "tenant"
                    ],
                    "serial": "1",
                    "ansible_ssh_user": "heat-admin",
                }
            },
            "overcloud": {
                "children": [
                    "DistributedComputeHCI"
                ],
                "vars": {
                    "storage_mgmt_vip": "192.168.24.20",
                    "container_cli": "podman",
                    "ctlplane_vip": "192.168.24.20",
                    "redis_vip": "192.168.24.24",
                    "internal_api_vip": "192.168.24.20",
                    "external_vip": "192.168.24.20",
                    "storage_vip": "192.168.24.20"
                }
            },
            "kernel": {
                "children": [
                    "DistributedComputeHCI"
                ],
                "vars": {
                    "ansible_ssh_user": "heat-admin"
                }
            },
            "ovn_controller": {
                "children": [
                    "DistributedComputeHCI"
                ],
                "vars": {
                    "ansible_ssh_user": "heat-admin"
                }
            },
            "_meta": {
                "hostvars": {
                    "edge0-distributedcomputehci-0": {
                        "storage_ip": "192.168.24.13",
                        "storage_mgmt_ip": "192.168.24.13",
                        "external_ip": "192.168.24.13",
                        "ctlplane_ip": "192.168.24.13",
                        "tenant_ip": "192.168.24.13",
                        "internal_api_ip": "192.168.24.13",
                        "management_ip": "192.168.24.13",
                        "ansible_host": "192.168.24.13"
                    }
                }
            }
        }

    def _mock_inv_merged_data(self):
        return {
            "Undercloud": {
                "hosts": {
                    "undercloud": {}
                },
                "vars": {
                    "username": "admin",
                    "overcloud_keystone_url": "http://192.168.24.21:5000",
                    "project_name": "admin",
                    "overcloud_horizon_url": "http://192.168.24.21/dashboard",
                    "auth_url": "https://192.168.24.2:13000",
                    "ansible_connection": "local",
                    "cacert": "/etc/pki/ca-trust/cm-local-ca.pem",
                    "ansible_host": "localhost",
                    "ansible_remote_tmp": "/tmp/ansible-${USER}",
                    "undercloud_service_list": [
                        "tripleo_nova_compute",
                        "tripleo_heat_engine",
                        "tripleo_ironic_conductor",
                        "tripleo_swift_container_server",
                        "tripleo_swift_object_server",
                        "tripleo_mistral_engine"
                    ],
                    "ansible_python_interpreter": "/usr/bin/python",
                    "overcloud_admin_password": "7uCCDn4lIKQ4i7ONsPdgX1KbC",
                    "plan": '',
                    "plans": [
                        "central",
                        "edge0"
                    ]
                }
            },
            "central_Controller": {
                "hosts": {
                    "central-controller-0": {
                        "storage_ip": "192.168.24.12",
                        "storage_mgmt_ip": "192.168.24.12",
                        "external_ip": "192.168.24.12",
                        "ctlplane_ip": "192.168.24.12",
                        "tenant_ip": "192.168.24.12",
                        "internal_api_ip": "192.168.24.12",
                        "management_ip": "192.168.24.12",
                        "ansible_host": "192.168.24.12"
                    }
                },
                "vars": {
                    "tripleo_role_name": "Controller",
                    "tripleo_role_networks": [
                        "management",
                        "storage",
                        "ctlplane",
                        "external",
                        "internal_api",
                        "storage_mgmt",
                        "tenant"
                    ],
                    "serial": "1",
                    "ansible_ssh_user": "heat-admin",
                }
            },
            "central_overcloud": {
                "vars": {
                    "storage_mgmt_vip": "192.168.24.21",
                    "container_cli": "podman",
                    "ctlplane_vip": "192.168.24.21",
                    "redis_vip": "192.168.24.11",
                    "internal_api_vip": "192.168.24.21",
                    "external_vip": "192.168.24.21",
                    "storage_vip": "192.168.24.21"
                },
                "children": {
                    "central_Controller": {}
                }
            },
            "central": {
                "vars": {
                    "storage_mgmt_vip": "192.168.24.21",
                    "container_cli": "podman",
                    "ctlplane_vip": "192.168.24.21",
                    "redis_vip": "192.168.24.11",
                    "internal_api_vip": "192.168.24.21",
                    "external_vip": "192.168.24.21",
                    "storage_vip": "192.168.24.21"
                },
                "children": {
                    "central_Controller": {}
                }
            },
            "central_kernel": {
                "vars": {
                    "ansible_ssh_user": "heat-admin"
                },
                "children": {
                    "central_Controller": {}
                }
            },
            "central_ovn_controller": {
                "vars": {
                    "ansible_ssh_user": "heat-admin"
                },
                "children": {
                    "central_Controller": {}
                }
            },
            "edge0_DistributedComputeHCI": {
                "hosts": {
                    "edge0-distributedcomputehci-0": {
                        "storage_ip": "192.168.24.13",
                        "storage_mgmt_ip": "192.168.24.13",
                        "external_ip": "192.168.24.13",
                        "ctlplane_ip": "192.168.24.13",
                        "tenant_ip": "192.168.24.13",
                        "internal_api_ip": "192.168.24.13",
                        "management_ip": "192.168.24.13",
                        "ansible_host": "192.168.24.13"
                    }
                },
                "vars": {
                    "tripleo_role_name": "DistributedComputeHCI",
                    "tripleo_role_networks": [
                        "management",
                        "storage",
                        "ctlplane",
                        "external",
                        "internal_api",
                        "storage_mgmt",
                        "tenant"
                    ],
                    "serial": "1",
                    "ansible_ssh_user": "heat-admin",
                }
            },
            "edge0_overcloud": {
                "vars": {
                    "storage_mgmt_vip": "192.168.24.20",
                    "container_cli": "podman",
                    "ctlplane_vip": "192.168.24.20",
                    "redis_vip": "192.168.24.24",
                    "internal_api_vip": "192.168.24.20",
                    "external_vip": "192.168.24.20",
                    "storage_vip": "192.168.24.20"
                },
                "children": {
                    "edge0_DistributedComputeHCI": {}
                }
            },
            "edge0": {
                "vars": {
                    "storage_mgmt_vip": "192.168.24.20",
                    "container_cli": "podman",
                    "ctlplane_vip": "192.168.24.20",
                    "redis_vip": "192.168.24.24",
                    "internal_api_vip": "192.168.24.20",
                    "external_vip": "192.168.24.20",
                    "storage_vip": "192.168.24.20"
                },
                "children": {
                    "edge0_DistributedComputeHCI": {}
                }
            },
            "edge0_kernel": {
                "vars": {
                    "ansible_ssh_user": "heat-admin"
                },
                "children": {
                    "edge0_DistributedComputeHCI": {}
                }
            },
            "edge0_ovn_controller": {
                "vars": {
                    "ansible_ssh_user": "heat-admin"
                },
                "children": {
                    "edge0_DistributedComputeHCI": {}
                }
            }
        }
