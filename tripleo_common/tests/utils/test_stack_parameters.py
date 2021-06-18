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

from unittest import mock

from ironicclient import exceptions as ironicexceptions

from tripleo_common.tests import base
from tripleo_common.utils import stack_parameters
from tripleo_common.utils import nodes


class StackParametersTest(base.TestCase):

    def test_generate_hostmap(self):

        # two instances in 'nova list'.
        # vm1 with id=123 and vm2 with id=234
        server1 = mock.MagicMock()
        server1.id = 123
        server1.name = 'vm1'

        server2 = mock.MagicMock()
        server2.id = 234
        server2.name = 'vm2'

        servers = mock.MagicMock()
        servers = [server1, server2]

        compute_client = mock.MagicMock()
        compute_client.servers.list.side_effect = (servers, )

        # we assume instance id=123 has been provisioned using bm node 'bm1'
        # while instance id=234 is in error state, so no bm node has been used

        def side_effect(args):
            if args == 123:
                return bm1
            if args == 234:
                raise ironicexceptions.NotFound

        baremetal_client = mock.MagicMock()
        baremetal_client.node.get_by_instance_uuid = mock.MagicMock(
            side_effect=side_effect)

        # bm server with name='bm1' and uuid='9876'
        bm1 = mock.MagicMock()
        bm1.uuid = 9876
        bm1.name = 'bm1'

        # 'bm1' has a single port with mac='aa:bb:cc:dd:ee:ff'
        port1 = mock.MagicMock()
        port1.address = 'aa:bb:cc:dd:ee:ff'

        def side_effect2(node, *args):
            if node == 9876:
                return [port1, ]
            raise ironicexceptions.NotFound

        baremetal_client.port.list = mock.MagicMock(side_effect=side_effect2)

        expected_hostmap = {
            'aa:bb:cc:dd:ee:ff': {
                'compute_name': 'vm1',
                'baremetal_name': 'bm1'
                }
            }

        result = nodes.generate_hostmap(baremetal_client, compute_client)
        self.assertEqual(result, expected_hostmap)

    @mock.patch('tripleo_common.utils.nodes.generate_hostmap')
    def test_generate_fencing_parameters(self, mock_generate_hostmap):
        test_hostmap = {
            "00:11:22:33:44:55": {
                "compute_name": "compute_name_0",
                "baremetal_name": "baremetal_name_0"
                },
            "11:22:33:44:55:66": {
                "compute_name": "compute_name_1",
                "baremetal_name": "baremetal_name_1"
                },
            "aa:bb:cc:dd:ee:ff": {
                "compute_name": "compute_name_4",
                "baremetal_name": "baremetal_name_4"
                },
            "bb:cc:dd:ee:ff:gg": {
                "compute_name": "compute_name_5",
                "baremetal_name": "baremetal_name_5"
                }
            }
        mock_generate_hostmap.return_value = test_hostmap

        test_envjson = [{
            "name": "control-0",
            "pm_password": "control-0-password",
            "pm_type": "ipmi",
            "pm_user": "control-0-admin",
            "pm_addr": "0.1.2.3",
            "pm_port": "0123",
            "ports": [
                {"address": "00:11:22:33:44:55"},
            ]
        }, {
            "name": "control-1",
            "pm_password": "control-1-password",
            # Still support deprecated drivers
            "pm_type": "pxe_ipmitool",
            "pm_user": "control-1-admin",
            "pm_addr": "1.2.3.4",
            "ports": [
                {"address": "11:22:33:44:55:66"}
            ]
        }, {
            # test node using redfish pm
            "name": "compute-4",
            "pm_password": "calvin",
            "pm_type": "redfish",
            "pm_user": "root",
            "pm_addr": "172.16.0.1:8000",
            "pm_port": "8000",
            "redfish_verify_ca": "false",
            "pm_system_id": "/redfish/v1/Systems/5678",
            "ports": [
                {"address": "aa:bb:cc:dd:ee:ff"}
            ]
        }, {
            # This is an extra node on oVirt/RHV
            "name": "control-3",
            "pm_password": "ovirt-password",
            "pm_type": "staging-ovirt",
            "pm_user": "admin@internal",
            "pm_addr": "3.4.5.6",
            "pm_vm_name": "control-3",
            "ports": [
                {"address": "bb:cc:dd:ee:ff:gg"}
            ]
        }, {
            # This is an extra node that is not in the hostmap, to ensure we
            # cope with unprovisioned nodes
            "name": "control-2",
            "pm_password": "control-2-password",
            "pm_type": "ipmi",
            "pm_user": "control-2-admin",
            "pm_addr": "2.3.4.5",
            "ports": [
                {"address": "22:33:44:55:66:77"}
            ]
        }
        ]

        result = stack_parameters.generate_fencing_parameters(
            test_envjson, 28, 5, 0, True)['parameter_defaults']

        self.assertTrue(result["EnableFencing"])
        self.assertEqual(len(result["FencingConfig"]["devices"]), 5)
        self.assertEqual(result["FencingConfig"]["devices"][0], {
                         "agent": "fence_ipmilan",
                         "host_mac": "00:11:22:33:44:55",
                         "params": {
                             "delay": 28,
                             "ipaddr": "0.1.2.3",
                             "ipport": "0123",
                             "lanplus": True,
                             "privlvl": 5,
                             "login": "control-0-admin",
                             "passwd": "control-0-password",
                             }
                         })
        self.assertEqual(result["FencingConfig"]["devices"][1], {
                         "agent": "fence_ipmilan",
                         "host_mac": "11:22:33:44:55:66",
                         "params": {
                             "delay": 28,
                             "ipaddr": "1.2.3.4",
                             "lanplus": True,
                             "privlvl": 5,
                             "login": "control-1-admin",
                             "passwd": "control-1-password",
                             }
                         })
        self.assertEqual(result["FencingConfig"]["devices"][2], {
                         "agent": "fence_redfish",
                         "host_mac": "aa:bb:cc:dd:ee:ff",
                         "params": {
                             "delay": 28,
                             "ipaddr": "172.16.0.1:8000",
                             "ipport": "8000",
                             "privlvl": 5,
                             "login": "root",
                             "passwd": "calvin",
                             "systems_uri": "/redfish/v1/Systems/5678",
                             "ssl_insecure": "true",
                             }
                         })
        self.assertEqual(result["FencingConfig"]["devices"][3], {
                         "agent": "fence_rhevm",
                         "host_mac": "bb:cc:dd:ee:ff:gg",
                         "params": {
                             "delay": 28,
                             "ipaddr": "3.4.5.6",
                             "login": "admin@internal",
                             "passwd": "ovirt-password",
                             "port": "control-3",
                             "ssl": 1,
                             "ssl_insecure": 1,
                             }
                         })

    def test_run_valid_network_config(self):
        mock_env = {
            'template': {},
            'files': {},
            'environment': [{'path': 'environments/test.yaml'}]
        }

        mock_heat = mock.MagicMock()

        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": "echo \'{\"network_config\": {}}\'"
                           " > /etc/os-net-config/config.json"}
            }])

        expected = {"network_config": {}}
        # Test
        result = stack_parameters.get_network_configs(
            mock_heat, mock_env, container='overcloud', role_name='Compute')
        self.assertEqual(expected, result)
        mock_heat.stacks.preview.assert_called_once_with(
            environment=[{'path': 'environments/test.yaml'}],
            files={},
            template={},
            stack_name='overcloud-TEMP',
        )

    def test_run_invalid_network_config(self):

        mock_env = {
            'template': {},
            'files': {},
            'environment': [{'path': 'environments/test.yaml'}]
        }
        mock_heat = mock.MagicMock()

        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": ""}
            }])

        # Test
        self.assertRaises(RuntimeError,
                          stack_parameters.get_network_configs,
                          mock_heat, mock_env, container='overcloud',
                          role_name='Compute')
        mock_heat.stacks.preview.assert_called_once_with(
            environment=[{'path': 'environments/test.yaml'}],
            files={},
            template={},
            stack_name='overcloud-TEMP',
        )

    def test_run_valid_network_config_with_no_if_routes_inputs(self):

        mock_env = {
            'template': {
                'resources': {
                    'ComputeGroupVars': {
                        'properties': {
                            'value': {
                                'role_networks': ['InternalApi',
                                                  'Storage']}
                        }
                    }
                }
            },
            'files': {},
            'environment': {'parameter_defaults': {}}
        }

        mock_heat = mock.MagicMock()

        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": "echo \'{\"network_config\": {}}\'"
                           " > /etc/os-net-config/config.json"}
            }])

        expected = {"network_config": {}}
        # Test
        result = stack_parameters.get_network_configs(
            mock_heat, mock_env, container='overcloud', role_name='Compute')
        self.assertEqual(expected, result)
        mock_heat.stacks.preview.assert_called_once_with(
            environment={
                'parameter_defaults': {
                    'InternalApiInterfaceRoutes': [[]],
                    'StorageInterfaceRoutes': [[]]
                }
            },
            files={},
            template={'resources': {'ComputeGroupVars': {'properties': {
                'value': {'role_networks': ['InternalApi', 'Storage']}
                }}}},
            stack_name='overcloud-TEMP',
        )

    def test_run_valid_network_config_with_if_routes_inputs(self):

        mock_env = {
            'template': {
                'resources': {
                    'ComputeGroupVars': {
                        'properties': {
                            'value': {
                                'role_networks': ['InternalApi',
                                                  'Storage']}
                        }
                    }
                }
            },
            'files': {},
            'environment': {
                'parameter_defaults': {
                    'InternalApiInterfaceRoutes': ['test1'],
                    'StorageInterfaceRoutes': ['test2']
                }}
        }

        mock_heat = mock.MagicMock()

        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": "echo \'{\"network_config\": {}}\'"
                           " > /etc/os-net-config/config.json"}
            }])

        expected = {"network_config": {}}
        # Test
        result = stack_parameters.get_network_configs(
            mock_heat, mock_env, container='overcloud', role_name='Compute')
        self.assertEqual(expected, result)
        mock_heat.stacks.preview.assert_called_once_with(
            environment={
                'parameter_defaults': {
                    'InternalApiInterfaceRoutes': ['test1'],
                    'StorageInterfaceRoutes': ['test2']
                }
            },
            files={},
            template={'resources': {'ComputeGroupVars': {'properties': {
                'value': {'role_networks': ['InternalApi', 'Storage']}
                }}}},
            stack_name='overcloud-TEMP',
        )
