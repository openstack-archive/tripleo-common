# Copyright 2016 Red Hat, Inc.
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
import mock
import yaml

from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import parameters
from tripleo_common import constants
from tripleo_common import exception
from tripleo_common.tests import base

_EXISTING_PASSWORDS = {
    'PlacementPassword': 'VFJeqBKbatYhQm9jja67hufft',
    'MistralPassword': 'VFJeqBKbatYhQm9jja67hufft',
    'BarbicanPassword': 'MGGQBtgKT7FnywvkcdMwE9nhx',
    'BarbicanSimpleCryptoKek': 'dGhpcnR5X3R3b19ieXRlX2tleWJsYWhibGFoYmxhaGg=',
    'AdminPassword': 'jFmY8FTpvtF2e4d4ReXvmUP8k',
    'CeilometerMeteringSecret': 'CbHTGK4md4Cc8P8ZyzTns6wry',
    'ZaqarPassword': 'bbFgCTFbAH8vf9n3xvZCP8aMR',
    'NovaPassword': '7dZATgVPwD7Ergs9kTTDMCr7F',
    'MysqlRootPassword': 'VqJYpEdKks',
    'RabbitCookie': 'BqJYpEdKksAqJYpEdKks',
    'HeatAuthEncryptionKey': '9xZXehsKc2HbmFFMKjuqxTJHn',
    'PcsdPassword': 'KjEzeitus8eu751a',
    'HorizonSecret': 'mjEzeitus8eu751B',
    'NovajoinPassword': '7dZATgVPwD7Ergs9kTTDMCr7F',
    'IronicPassword': '4hFDgn9ANeVfuqk84pHpD4ksa',
    'RedisPassword': 'xjj3QZDcUQmU6Q7NzWBHRUhGd',
    'SaharaPassword': 'spFvYGezdFwnTk7NPxgYTbUPh',
    'AdminToken': 'jq6G6HyZtj7dcZEvuyhAfjutM',
    'CinderPassword': 'dcxC3xyUcrmvzfrrxpAd3REcm',
    'CongressPassword': 'DwcKvMqXMuNYYFU4zTCuG4234',
    'GlancePassword': 'VqJYNEdKKsGZtgnHct77XBtrV',
    'RabbitPassword': 'ahuHRXdPMx9rzCdjD9CJJNCgA',
    'RpcPassword': 'ahuHRXdPMx9rzCdjD9CJJNCgA',
    'NotifyPassword': 'ahuHRXdPMx9rzCdjD9CJJNCgA',
    'CephAdminKey': b'AQCQXtlXAAAAABAAT4Gk+U8EqqStL+JFa9bp1Q==',
    'HAProxyStatsPassword': 'P8tbdK6n4YUkTaUyy8XgEVTe6',
    'CeilometerPassword': 'RRdpwK6qf2pbKz2UtzxqauAdk',
    'GnocchiPassword': 'cRYHcUkMuJeK3vyU9pCaznUZc',
    'HeatStackDomainAdminPassword': 'GgTRyWzKYsxK4mReTJ4CM6sMc',
    'CephRgwKey': b'AQCQXtlXAAAAABAAUKcqUMu6oMjAXMjoUV4/3A==',
    'AodhPassword': '8VZXehsKc2HbmFFMKYuqxTJHn',
    'PankoPassword': 'cVZXehsSc2KdmFFMKDudxTLKn',
    'OctaviaHeartbeatKey': 'oct-heartbeat-key',
    'OctaviaPassword': 'NMl7j3nKk1VVwMxUZC8Cgw==',
    'OctaviaServerCertsKeyPassphrase': 'aW5zZWN1cmUta2V5LWRvLW5vdC11c2U=',
    'OctaviaCaKeyPassphrase': 'SLj4c3uCk4DDxPwQOG1Heb==',
    'ManilaPassword': 'NYJN86Fua3X8AVFWmMhQa2zTH',
    'NeutronMetadataProxySharedSecret': 'Q2YgUCwmBkYdqsdhhCF4hbghu',
    'CephMdsKey': b'AQCQXtlXAAAAABAAT4Gk+U8EqqStL+JFa9bp1Q==',
    'CephManilaClientKey': b'AQANOFFY1NW6AxAAu6jWI3YSOsp2QWusb5Y3DQ==',
    'CephMonKey': b'AQCQXtlXAAAAABAA9l+59N3yH+C49Y0JiKeGFg==',
    'CephGrafanaAdminPassword': 'NYJN86Fua3X8AVFWmMhQa2zTH',
    'CephDashboardAdminPassword': 'NYJN86Fua3X8AVFWmMhQa2zTH',
    'SwiftHashSuffix': 'td8mV6k7TYEGKCDvjVBwckpn9',
    'SnmpdReadonlyUserPassword': 'TestPassword',
    'SwiftPassword': 'z6EWAVfW7CuxvKdzjWTdrXCeg',
    'HeatPassword': 'bREnsXtMHKTHxt8XW6NXAYr48',
    'MysqlClustercheckPassword': 'jN4RMMWWJ4sycaRwh7UvrAtfX',
    'CephClientKey': b'AQCQXtlXAAAAABAAKyc+8St8i9onHyu2mPk+vg==',
    'NeutronPassword': 'ZxAjdU2UXCV4GM3WyPKrzAZXD',
    'DesignatePassword': 'wHYj7rftFzHMpJKnGxbjjR9CW',
    'DesignateRndcKey': 'hB8XaZRd2Tf00jKsyoXpyw==',
    'KeystoneCredential0': 'ftJNQ_XlDUK7Lgvv1kdWf3SyqVsrvNDgoNV4kJg3yzw=',
    'KeystoneCredential1': 'c4MFq82TQLFLKpiiUjrKkp15dafE2ALcD3jbaIu3rfE=',
    'KeystoneFernetKey0': 'O8NSPxr4zXBBAoGIj-5aUmtE7-Jk5a4ptVsEhzJ8Vd8=',
    'KeystoneFernetKey1': 'AueoL37kd6eLjV29AG-Ruxu5szW47osgXx6aPOqtI6I=',
    'KeystoneFernetKeys': {
        '/etc/keystone/fernet-keys/0': {'content': 'IAMAVERYSAFEKEY'},
        '/etc/keystone/fernet-keys/1': {'content': 'IALSOAMAVERYSAFEKEY'}
    },
    'CephClusterFSID': u'97c16f44-b62c-11e6-aed3-185e0f73fdc5',
    'Ec2ApiPassword': 'FPvz2WiWxrHVWrmSSvv44bqmr',
    'EtcdInitialClusterToken': 'fcVZXehsSc2KdmFFMKDudxTLKa',
    'PacemakerRemoteAuthkey':
        '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'
        'sGhUtCQVed7dtj12',
    'MigrationSshKey': {
        'private_key': 'private_key',
        'public_key': 'public_key'
        },
    'LibvirtTLSPassword': 'xCdt9yeamKz8Fb6EGba9u82XU',
}


class GetPasswordsActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_password_from_parameter_defaults(self,
                                              mock_get_object_client,
                                              mock_get_orchestration_client):

        mock_ctx = mock.MagicMock()

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            "name": constants.DEFAULT_CONTAINER_NAME,
            "parameter_defaults": _EXISTING_PASSWORDS,
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)
        mock_get_object_client.return_value = swift

        mock_orchestration = mock.MagicMock()
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GetPasswordsAction()
        result = action.run(mock_ctx)

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_password_from_generated_passwords(self,
                                               mock_get_object_client,
                                               mock_get_orchestration_client):

        mock_ctx = mock.MagicMock()

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            "name": constants.DEFAULT_CONTAINER_NAME,
            "parameter_defaults": {},
            "passwords": _EXISTING_PASSWORDS,

        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)
        mock_get_object_client.return_value = swift

        mock_orchestration = mock.MagicMock()
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GetPasswordsAction()
        result = action.run(mock_ctx)

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_password_merging_passwords(self,
                                        mock_get_object_client,
                                        mock_get_orchestration_client):

        parameter_defaults = _EXISTING_PASSWORDS.copy()
        passwords = {"AdminPassword": parameter_defaults.pop("AdminPassword")}

        mock_ctx = mock.MagicMock()

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            "name": constants.DEFAULT_CONTAINER_NAME,
            "parameter_defaults": parameter_defaults,
            "passwords": passwords
        }, default_flow_style=False)

        swift.get_object.return_value = ({}, mock_env)
        mock_get_object_client.return_value = swift

        mock_orchestration = mock.MagicMock()
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GetPasswordsAction()
        result = action.run(mock_ctx)

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)


class GetProfileOfFlavorActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.parameters.get_profile_of_flavor')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    def test_profile_found(self, mock_get_compute_client,
                           mock_get_profile_of_flavor):
        mock_ctx = mock.MagicMock()
        mock_get_profile_of_flavor.return_value = 'compute'
        action = parameters.GetProfileOfFlavorAction('oooq_compute')
        result = action.run(mock_ctx)
        expected_result = "compute"
        self.assertEqual(result, expected_result)

    @mock.patch('tripleo_common.utils.parameters.get_profile_of_flavor')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    def test_profile_not_found(self, mock_get_compute_client,
                               mock_get_profile_of_flavor):
        mock_ctx = mock.MagicMock()
        profile = (exception.DeriveParamsError, )
        mock_get_profile_of_flavor.side_effect = profile
        action = parameters.GetProfileOfFlavorAction('no_profile')
        result = action.run(mock_ctx)
        self.assertTrue(result.is_error())
        mock_get_profile_of_flavor.assert_called_once()


class GetNetworkConfigActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_valid_network_config(
            self, mock_get_object_client, mock_get_workflow_client,
            mock_get_orchestration_client, mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_cache_get,
            mock_cache_set):

        mock_ctx = mock.MagicMock()
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
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": "echo \'{\"network_config\": {}}\'"
                           " > /etc/os-net-config/config.json"}
            }])

        mock_get_orchestration_client.return_value = mock_heat

        mock_cache_get.return_value = None
        expected = {"network_config": {}}
        # Test
        action = parameters.GetNetworkConfigAction(container='overcloud',
                                                   role_name='Compute')
        result = action.run(mock_ctx)
        self.assertEqual(expected, result)
        mock_heat.stacks.preview.assert_called_once_with(
            environment={},
            files={},
            template={'heat_template_version': '2016-04-30'},
            stack_name='overcloud-TEMP',
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_valid_network_config_with_no_interface_routes_inputs(
            self, mock_get_object_client, mock_get_workflow_client,
            mock_get_orchestration_client, mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_cache_get,
            mock_cache_set):

        mock_ctx = mock.MagicMock()
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
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30',
            'resources': {'ComputeGroupVars': {'properties': {
                'value': {'role_networks': ['InternalApi', 'Storage']}
                }
            }}
        })
        mock_process_multiple_environments_and_files.return_value = (
            {}, {'parameter_defaults': {}})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": "echo \'{\"network_config\": {}}\'"
                           " > /etc/os-net-config/config.json"}
            }])

        mock_get_orchestration_client.return_value = mock_heat

        mock_cache_get.return_value = None
        expected = {"network_config": {}}
        # Test
        action = parameters.GetNetworkConfigAction(container='overcloud',
                                                   role_name='Compute')
        result = action.run(mock_ctx)
        self.assertEqual(expected, result)
        mock_heat.stacks.preview.assert_called_once_with(
            environment={'parameter_defaults': {
                'InternalApiInterfaceRoutes': [[]],
                'StorageInterfaceRoutes': [[]]}},
            files={},
            template={'heat_template_version': '2016-04-30',
                      'resources': {'ComputeGroupVars': {
                          'properties': {'value': {
                              'role_networks': ['InternalApi',
                                                'Storage']}}}}},
            stack_name='overcloud-TEMP',
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_valid_network_config_with_interface_routes_inputs(
            self, mock_get_object_client, mock_get_workflow_client,
            mock_get_orchestration_client, mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_cache_get,
            mock_cache_set):

        mock_ctx = mock.MagicMock()
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
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30',
            'resources': {'ComputeGroupVars': {'properties': {
                'value': {'role_networks': ['InternalApi', 'Storage']}}}}
        })
        mock_process_multiple_environments_and_files.return_value = (
            {}, {'parameter_defaults': {
                'InternalApiInterfaceRoutes': ['test1'],
                'StorageInterfaceRoutes': ['test2']}})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": "echo \'{\"network_config\": {}}\'"
                           " > /etc/os-net-config/config.json"}
            }])

        mock_get_orchestration_client.return_value = mock_heat

        mock_cache_get.return_value = None
        expected = {"network_config": {}}
        # Test
        action = parameters.GetNetworkConfigAction(container='overcloud',
                                                   role_name='Compute')
        result = action.run(mock_ctx)
        self.assertEqual(expected, result)
        mock_heat.stacks.preview.assert_called_once_with(
            environment={'parameter_defaults': {
                'InternalApiInterfaceRoutes': ['test1'],
                'StorageInterfaceRoutes': ['test2']}},
            files={},
            template={'heat_template_version': '2016-04-30',
                      'resources': {'ComputeGroupVars': {'properties': {
                          'value': {'role_networks': ['InternalApi',
                                                      'Storage']}}}}},
            stack_name='overcloud-TEMP',
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_invalid_network_config(
            self, mock_get_object_client,
            mock_get_workflow_client, mock_get_orchestration_client,
            mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_cache_get, mock_cache_set):

        mock_ctx = mock.MagicMock()
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
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": ""}
            }])

        mock_get_orchestration_client.return_value = mock_heat

        mock_cache_get.return_value = None
        # Test
        action = parameters.GetNetworkConfigAction(container='overcloud',
                                                   role_name='Compute')
        result = action.run(mock_ctx)
        self.assertTrue(result.is_error())
        mock_heat.stacks.preview.assert_called_once_with(
            environment={},
            files={},
            template={'heat_template_version': '2016-04-30'},
            stack_name='overcloud-TEMP',
        )
