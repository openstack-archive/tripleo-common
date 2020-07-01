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

import yaml

from swiftclient import exceptions as swiftexceptions
from ironicclient import exceptions as ironicexceptions

from tripleo_common import constants
from tripleo_common.tests import base
from tripleo_common.utils import stack_parameters
from tripleo_common.utils import nodes


class StackParametersTest(base.TestCase):

    @mock.patch('tripleo_common.utils.plan.'
                'cache_delete')
    def test_reset_parameter(self, mock_cache):
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'SomeTestParameter': 42}
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)

        # Test
        stack_parameters.reset_parameters(swift)

        mock_env_reset = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_called_once_with(
            constants.DEFAULT_CONTAINER_NAME,
            constants.PLAN_ENVIRONMENT,
            mock_env_reset
        )
        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get"
        )

    @mock.patch('uuid.uuid4')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.'
                'get_template_contents')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    def test_update_parameters(self, mock_cache,
                               mock_get_template_contents,
                               mock_env_files,
                               mock_uuid):

        mock_env_files.return_value = ({}, {})

        swift = mock.MagicMock(url="http://test.com")

        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }, default_flow_style=False)

        mock_roles = yaml.safe_dump([{"name": "foo"}])
        mock_network = yaml.safe_dump([{'enabled': False}])
        mock_exclude = yaml.safe_dump({"name": "foo"})

        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        def return_container_files(*args):
            return ('headers', [{'name': 'foo.role.j2.yaml'}])

        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)

        mock_heat = mock.MagicMock()

        mock_heat.stacks.validate.return_value = {
            "Type": "Foo",
            "Description": "Le foo bar",
            "Parameters": {"bar": {"foo": "bar barz"}},
            "NestedParameters": {"Type": "foobar"}
        }

        mock_uuid.return_value = "cheese"

        expected_value = {
            'environment_parameters': None,
            'heat_resource_tree': {
                'parameters': {'bar': {'foo': 'bar barz',
                                       'name': 'bar'}},
                'resources': {'cheese': {
                    'id': 'cheese',
                    'name': 'Root',
                    'description': 'Le foo bar',
                    'parameters': ['bar'],
                    'resources': ['cheese'],
                    'type': 'Foo'}
                }
            }
        }

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })

        # Test
        test_parameters = {'SomeTestParameter': 42}
        result = stack_parameters.update_parameters(
            swift, mock_heat, test_parameters)

        mock_env_updated = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'parameter_defaults': {'SomeTestParameter': 42},
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_any_call(
            constants.DEFAULT_CONTAINER_NAME,
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        mock_heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )

        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get",
            expected_value
        )
        self.assertEqual(result, expected_value)

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.'
                'get_template_contents')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    def test_update_parameter_new_key(self, mock_cache,
                                      mock_get_template_contents,
                                      mock_env_files):

        mock_env_files.return_value = ({}, {})

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }, default_flow_style=False)

        mock_roles = yaml.safe_dump([{"name": "foo"}])
        mock_network = yaml.safe_dump([{'enabled': False}])
        mock_exclude = yaml.safe_dump({"name": "foo"})

        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        def return_container_files(*args):
            return ('headers', [{'name': 'foo.role.j2.yaml'}])

        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)

        heat = mock.MagicMock()
        heat.stacks.validate.return_value = {}

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })

        # Test
        test_parameters = {'SomeTestParameter': 42}
        stack_parameters.update_parameters(
            swift, heat, test_parameters,
            parameter_key='test_key')
        mock_env_updated = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'test_key': {'SomeTestParameter': 42},
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_any_call(
            constants.DEFAULT_CONTAINER_NAME,
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )

        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get",
            {'environment_parameters': None, 'heat_resource_tree': {}}
        )

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.'
                'get_template_contents')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.parameters.set_count_and_flavor_params')
    def test_update_role_parameter(self, mock_set_count_and_flavor,
                                   mock_cache, mock_get_template_contents,
                                   mock_env_files):

        mock_env_files.return_value = ({}, {})

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': 'overcast'
        }, default_flow_style=False)

        mock_roles = yaml.safe_dump([{"name": "foo"}])
        mock_network = yaml.safe_dump([{'enabled': False}])
        mock_exclude = yaml.safe_dump({"name": "foo"})

        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        def return_container_files(*args):
            return ('headers', [{'name': 'foo.yaml'}])

        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)

        heat = mock.MagicMock()
        ironic = mock.MagicMock()
        compute = mock.MagicMock()

        heat.stacks.validate.return_value = {}

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })

        params = {'CephStorageCount': 1,
                  'OvercloudCephStorageFlavor': 'ceph-storage'}
        mock_set_count_and_flavor.return_value = params

        stack_parameters.update_role_parameters(
            swift, heat, ironic, compute,
            'ceph-storage', 'overcast')
        mock_env_updated = yaml.safe_dump({
            'name': 'overcast',
            'parameter_defaults': params
        }, default_flow_style=False)

        swift.put_object.assert_any_call(
            'overcast',
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )

        mock_cache.assert_called_once_with(
            swift,
            "overcast",
            "tripleo.parameters.get",
            {'environment_parameters': None, 'heat_resource_tree': {}}
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_empty_resource_tree(self,
                                 mock_get_template_contents,
                                 mock_process_multiple_environments_and_files,
                                 mock_cache_get,
                                 mock_cache_set):

        mock_cache_get.return_value = None
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            swiftexceptions.ClientException('atest2'),
            ({}, mock_env)
        )
        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.validate.return_value = {}

        expected_value = {
            'heat_resource_tree': {},
            'environment_parameters': None,
        }

        # Test
        result = stack_parameters.get_flattened_parameters(swift, mock_heat)
        mock_heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )
        self.assertEqual(result, expected_value)

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('uuid.uuid4', side_effect=['1', '2'])
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_valid_resource_tree(self,
                                 mock_get_template_contents,
                                 mock_process_multiple_environments_and_files,
                                 mock_uuid,
                                 mock_cache_get,
                                 mock_cache_set):

        mock_cache_get.return_value = None
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            swiftexceptions.ClientException('atest2'),
            ({}, mock_env)
        )
        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.validate.return_value = {
            'NestedParameters': {
                'CephStorageHostsDeployment': {
                    'Type': 'OS::Heat::StructuredDeployments',
                },
            },
            'description': 'sample',
            'Parameters': {
                'ControllerCount': {
                    'Default': 1,
                    'Type': 'Number',
                },
            }
        }

        expected_value = {
            'heat_resource_tree': {
                'resources': {
                    '1': {
                        'id': '1',
                        'name': 'Root',
                        'resources': [
                            '2'
                        ],
                        'parameters': [
                            'ControllerCount'
                        ]
                    },
                    '2': {
                        'id': '2',
                        'name': 'CephStorageHostsDeployment',
                        'type': 'OS::Heat::StructuredDeployments'
                    }
                },
                'parameters': {
                    'ControllerCount': {
                        'default': 1,
                        'type': 'Number',
                        'name': 'ControllerCount'
                    }
                },
            },
            'environment_parameters': None,
        }

        # Test
        result = stack_parameters.get_flattened_parameters(swift, mock_heat)
        self.assertEqual(result, expected_value)

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
            elif args == 234:
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
            else:
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
            "mac": [
                "00:11:22:33:44:55"
            ]
        }, {
            "name": "control-1",
            "pm_password": "control-1-password",
            # Still support deprecated drivers
            "pm_type": "pxe_ipmitool",
            "pm_user": "control-1-admin",
            "pm_addr": "1.2.3.4",
            "mac": [
                "11:22:33:44:55:66"
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
            "mac": [
                "aa:bb:cc:dd:ee:ff"
            ]
        }, {
            # This is an extra node on oVirt/RHV
            "name": "control-3",
            "pm_password": "ovirt-password",
            "pm_type": "staging-ovirt",
            "pm_user": "admin@internal",
            "pm_addr": "3.4.5.6",
            "pm_vm_name": "control-3",
            "mac": [
                "bb:cc:dd:ee:ff:gg"
            ]
        }, {
            # This is an extra node that is not in the hostmap, to ensure we
            # cope with unprovisioned nodes
            "name": "control-2",
            "pm_password": "control-2-password",
            "pm_type": "ipmi",
            "pm_user": "control-2-admin",
            "pm_addr": "2.3.4.5",
            "mac": [
                "22:33:44:55:66:77"
            ]
        }
        ]

        ironic = mock.MagicMock()
        compute = mock.MagicMock()

        result = stack_parameters.generate_fencing_parameters(
            ironic, compute, test_envjson,
            28, 5, 0, True)['parameter_defaults']

        self.assertTrue(result["EnableFencing"])
        self.assertEqual(len(result["FencingConfig"]["devices"]), 4)
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
                             "pcmk_host_list": "compute_name_0"
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
                             "pcmk_host_list": "compute_name_1"
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
                             "pcmk_host_list": "compute_name_4"
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
                             "pcmk_host_list": "compute_name_5"
                             }
                         })
