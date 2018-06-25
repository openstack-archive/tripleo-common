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
from tripleo_common.utils import passwords as password_utils

_EXISTING_PASSWORDS = {
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
    'CephAdminKey': b'AQCQXtlXAAAAABAAT4Gk+U8EqqStL+JFa9bp1Q==',
    'HAProxyStatsPassword': 'P8tbdK6n4YUkTaUyy8XgEVTe6',
    'TackerPassword': 'DwcKvMqXMuNYYFU4zTCuG4234',
    'TrovePassword': 'V7A7zegkMdRFnYuN23gdc4KQC',
    'CeilometerPassword': 'RRdpwK6qf2pbKz2UtzxqauAdk',
    'GnocchiPassword': 'cRYHcUkMuJeK3vyU9pCaznUZc',
    'HeatStackDomainAdminPassword': 'GgTRyWzKYsxK4mReTJ4CM6sMc',
    'CephRgwKey': b'AQCQXtlXAAAAABAAUKcqUMu6oMjAXMjoUV4/3A==',
    'AodhPassword': '8VZXehsKc2HbmFFMKYuqxTJHn',
    'PankoPassword': 'cVZXehsSc2KdmFFMKDudxTLKn',
    'OctaviaHeartbeatKey': 'oct-heartbeat-key',
    'OctaviaPassword': 'NMl7j3nKk1VVwMxUZC8Cgw==',
    'OctaviaCaKeyPassphrase': 'SLj4c3uCk4DDxPwQOG1Heb==',
    'ManilaPassword': 'NYJN86Fua3X8AVFWmMhQa2zTH',
    'NeutronMetadataProxySharedSecret': 'Q2YgUCwmBkYdqsdhhCF4hbghu',
    'CephMdsKey': b'AQCQXtlXAAAAABAAT4Gk+U8EqqStL+JFa9bp1Q==',
    'CephManilaClientKey': b'AQANOFFY1NW6AxAAu6jWI3YSOsp2QWusb5Y3DQ==',
    'CephMonKey': b'AQCQXtlXAAAAABAA9l+59N3yH+C49Y0JiKeGFg==',
    'SwiftHashSuffix': 'td8mV6k7TYEGKCDvjVBwckpn9',
    'SnmpdReadonlyUserPassword': 'TestPassword',
    'SwiftPassword': 'z6EWAVfW7CuxvKdzjWTdrXCeg',
    'HeatPassword': 'bREnsXtMHKTHxt8XW6NXAYr48',
    'MysqlClustercheckPassword': 'jN4RMMWWJ4sycaRwh7UvrAtfX',
    'CephClientKey': b'AQCQXtlXAAAAABAAKyc+8St8i9onHyu2mPk+vg==',
    'NeutronPassword': 'ZxAjdU2UXCV4GM3WyPKrzAZXD',
    'DesignatePassword': 'wHYj7rftFzHMpJKnGxbjjR9CW',
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
    'OpenDaylightPassword': 'abc487gfh017rmviuq75jdiw7',
}


class GetParametersActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_set')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, mock_get_object_client,
                 mock_get_orchestration_client,
                 mock_get_template_contents,
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
        mock_heat.stacks.validate.return_value = {}
        mock_get_orchestration_client.return_value = mock_heat

        mock_cache_get.return_value = None
        # Test
        action = parameters.GetParametersAction()
        action.run(mock_ctx)
        mock_heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )
        mock_cache_get.assert_called_once_with(
            mock_ctx,
            "overcloud",
            "tripleo.parameters.get"
        )
        mock_cache_set.assert_called_once_with(
            mock_ctx,
            "overcloud",
            "tripleo.parameters.get",
            {'heat_resource_tree': {}, 'environment_parameters': None}
        )


class ResetParametersActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_delete')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, mock_get_object_client, mock_cache):

        mock_ctx = mock.MagicMock()

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'SomeTestParameter': 42}
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)
        mock_get_object_client.return_value = swift

        # Test
        action = parameters.ResetParametersAction()

        action.run(mock_ctx)

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
            mock_ctx,
            "overcloud",
            "tripleo.parameters.get"
        )


class UpdateParametersActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.parameters.uuid')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.'
                'get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_set')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_run(self, mock_get_orchestration_client_client,
                 mock_get_object_client, mock_cache,
                 mock_get_template_contents, mock_env_files,
                 mock_uuid):

        mock_env_files.return_value = ({}, {})

        mock_ctx = mock.MagicMock()

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

        mock_get_object_client.return_value = swift

        mock_heat = mock.MagicMock()
        mock_get_orchestration_client_client.return_value = mock_heat

        mock_heat.stacks.validate.return_value = {
            "Type": "Foo",
            "Description": "Le foo bar",
            "Parameters": {"bar": {"foo": "bar barz"}},
            "NestedParameters": {"Type": "foobar"}
        }

        mock_uuid.uuid4.return_value = "cheese"

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
        action = parameters.UpdateParametersAction(test_parameters)
        return_value = action.run(mock_ctx)

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
            mock_ctx,
            "overcloud",
            "tripleo.parameters.get",
            expected_value
        )
        self.assertEqual(return_value, expected_value)

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.'
                'get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_set')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_run_new_key(self, mock_get_orchestration_client_client,
                         mock_get_object_client, mock_cache,
                         mock_get_template_contents, mock_env_files):

        mock_env_files.return_value = ({}, {})

        mock_ctx = mock.MagicMock()

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

        mock_get_object_client.return_value = swift

        heat = mock.MagicMock()
        heat.stacks.validate.return_value = {}
        mock_get_orchestration_client_client.return_value = heat

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })

        # Test
        test_parameters = {'SomeTestParameter': 42}
        action = parameters.UpdateParametersAction(test_parameters,
                                                   key='test_key')
        action.run(mock_ctx)

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
            mock_ctx,
            "overcloud",
            "tripleo.parameters.get",
            {'environment_parameters': None, 'heat_resource_tree': {}}
        )


class UpdateRoleParametersActionTest(base.TestCase):

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.'
                'get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_set')
    @mock.patch('tripleo_common.utils.parameters.set_count_and_flavor_params')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_baremetal_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_run(self, mock_get_orchestration_client_client,
                 mock_get_object_client, mock_get_compute_client,
                 mock_get_baremetal_client, mock_set_count_and_flavor,
                 mock_cache, mock_get_template_contents, mock_env_files):

        mock_env_files.return_value = ({}, {})

        mock_ctx = mock.MagicMock()

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

        mock_get_object_client.return_value = swift

        heat = mock.MagicMock()
        heat.stacks.validate.return_value = {}
        mock_get_orchestration_client_client.return_value = heat

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })

        params = {'CephStorageCount': 1,
                  'OvercloudCephStorageFlavor': 'ceph-storage'}
        mock_set_count_and_flavor.return_value = params

        action = parameters.UpdateRoleParametersAction('ceph-storage',
                                                       'overcast')
        action.run(mock_ctx)

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
            mock_ctx,
            "overcast",
            "tripleo.parameters.get",
            {'environment_parameters': None, 'heat_resource_tree': {}}
        )


class GeneratePasswordsActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_delete')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client', return_value="TestPassword")
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, mock_get_object_client,
                 mock_get_workflow_client,
                 mock_get_snmpd_readonly_user_password,
                 mock_get_orchestration_client, mock_cache):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_ctx = mock.MagicMock()

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': 'overcast',
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)
        mock_get_object_client.return_value = swift

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }
        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'value': 'existing_value'
        }
        mock_orchestration.resources.get.return_value = mock_resource
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GeneratePasswordsAction()
        result = action.run(mock_ctx)

        for password_param_name in constants.PASSWORD_PARAMETER_NAMES:
            self.assertTrue(password_param_name in result,
                            "%s is not in %s" % (password_param_name, result))

            if password_param_name in \
                    constants.LEGACY_HEAT_PASSWORD_RESOURCE_NAMES:
                self.assertEqual(result[password_param_name], 'existing_value')
            else:
                self.assertNotEqual(result[password_param_name],
                                    'existing_value')

        mock_cache.assert_called_once_with(
            mock_ctx,
            "overcloud",
            "tripleo.parameters.get"
        )

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_delete')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_passwords_exist(self, mock_get_object_client,
                                 mock_get_workflow_client,
                                 mock_get_snmpd_readonly_user_password,
                                 mock_fernet_keys_setup,
                                 mock_create_ssh_keypair,
                                 mock_get_orchestration_client,
                                 mock_cache):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        mock_ctx = mock.MagicMock()

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'passwords': _EXISTING_PASSWORDS.copy()
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)
        mock_get_object_client.return_value = swift

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GeneratePasswordsAction()
        result = action.run(mock_ctx)

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)
        mock_cache.assert_called_once_with(
            mock_ctx,
            "overcloud",
            "tripleo.parameters.get"
        )

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_delete')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_passwords_exist_in_heat(self, mock_get_object_client,
                                     mock_get_workflow_client,
                                     mock_get_snmpd_readonly_user_password,
                                     mock_fernet_keys_setup,
                                     mock_create_ssh_keypair,
                                     mock_get_orchestration_client,
                                     mock_cache):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        existing_passwords = _EXISTING_PASSWORDS.copy()
        existing_passwords.pop("AdminPassword")

        mock_ctx = mock.MagicMock()
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'passwords': existing_passwords.copy()
        }, default_flow_style=False)

        swift.get_object.return_value = ({}, mock_env)
        mock_get_object_client.return_value = swift

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {
                'AdminPassword': 'ExistingPasswordInHeat',
            }
        }
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GeneratePasswordsAction()
        result = action.run(mock_ctx)

        existing_passwords["AdminPassword"] = "ExistingPasswordInHeat"
        # ensure old passwords used and no new generation
        self.assertEqual(existing_passwords, result)
        mock_cache.assert_called_once_with(
            mock_ctx,
            "overcloud",
            "tripleo.parameters.get"
        )


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


class GenerateFencingParametersActionTestCase(base.TestCase):

    @mock.patch('tripleo_common.utils.nodes.generate_hostmap')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_baremetal_client')
    def test_no_success(self, mock_get_baremetal, mock_get_compute,
                        mock_generate_hostmap):
        mock_ctx = mock.MagicMock()
        test_hostmap = {
            "00:11:22:33:44:55": {
                "compute_name": "compute_name_0",
                "baremetal_name": "baremetal_name_0"
                },
            "11:22:33:44:55:66": {
                "compute_name": "compute_name_1",
                "baremetal_name": "baremetal_name_1"
                }
            }
        mock_generate_hostmap.return_value = test_hostmap

        test_envjson = [{
            "name": "control-0",
            "pm_password": "control-0-password",
            "pm_type": "pxe_ipmitool",
            "pm_user": "control-0-admin",
            "pm_addr": "0.1.2.3",
            "pm_port": "0123",
            "mac": [
                "00:11:22:33:44:55"
            ]
        }, {
            "name": "control-1",
            "pm_password": "control-1-password",
            "pm_type": "pxe_ssh",
            "pm_user": "control-1-admin",
            "pm_addr": "1.2.3.4",
            "mac": [
                "11:22:33:44:55:66"
            ]
        }, {
            # This is an extra node that is not in the hostmap, to ensure we
            # cope with unprovisioned nodes
            "name": "control-2",
            "pm_password": "control-2-password",
            "pm_type": "pxe_ipmitool",
            "pm_user": "control-2-admin",
            "pm_addr": "2.3.4.5",
            "mac": [
                "22:33:44:55:66:77"
            ]
        }]
        test_osauth = {
            "auth_url": "test://auth.url",
            "login": "test_os_username",
            "passwd": "test_os_password",
            "tenant_name": "test_os_tenant_name",
            }

        action = parameters.GenerateFencingParametersAction(test_envjson,
                                                            test_osauth,
                                                            28,
                                                            5,
                                                            0,
                                                            True)

        result = action.run(mock_ctx)["parameter_defaults"]

        self.assertTrue(result["EnableFencing"])
        self.assertEqual(len(result["FencingConfig"]["devices"]), 2)
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
                         "agent": "fence_ironic",
                         "host_mac": "11:22:33:44:55:66",
                         "params": {
                             "auth_url": "test://auth.url",
                             "delay": 28,
                             "login": "test_os_username",
                             "passwd": "test_os_password",
                             "tenant_name": "test_os_tenant_name",
                             "pcmk_host_map": "compute_name_1:baremetal_name_1"
                             }
                         })


class GetFlattenedParametersActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_set')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_empty_resource_tree(self, mock_get_object_client,
                                 mock_get_orchestration_client,
                                 mock_get_template_contents,
                                 mock_process_multiple_environments_and_files,
                                 mock_cache_get,
                                 mock_cache_set):

        mock_ctx = mock.MagicMock()
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
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_get_orchestration_client.return_value = mock_heat

        mock_heat.stacks.validate.return_value = {}

        expected_value = {
            'heat_resource_tree': {},
            'environment_parameters': None,
        }

        # Test
        action = parameters.GetFlattenedParametersAction()
        result = action.run(mock_ctx)
        mock_heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )
        self.assertEqual(result, expected_value)

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_set')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_get')
    @mock.patch('uuid.uuid4', side_effect=['1', '2'])
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_valid_resource_tree(self, mock_get_object_client,
                                 mock_get_orchestration_client,
                                 mock_get_template_contents,
                                 mock_process_multiple_environments_and_files,
                                 mock_uuid,
                                 mock_cache_get,
                                 mock_cache_set):

        mock_ctx = mock.MagicMock()
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
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_get_orchestration_client.return_value = mock_heat

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
        action = parameters.GetFlattenedParametersAction()
        result = action.run(mock_ctx)
        self.assertEqual(result, expected_value)


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


class RotateFernetKeysActionTest(base.TestCase):

    def test_get_next_index(self):
        action = parameters.RotateFernetKeysAction()
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'Some key'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'Some other key'},
        }
        next_index = action.get_next_index(keys_map)
        self.assertEqual(next_index, 2)

    @mock.patch('tripleo_common.utils.passwords.'
                'create_keystone_credential')
    def test_rotate_keys(self, mock_keystone_creds):
        action = parameters.RotateFernetKeysAction()
        mock_keystone_creds.return_value = 'Some new key'

        staged_key_index = password_utils.KEYSTONE_FERNET_REPO + '0'
        new_primary_key_index = password_utils.KEYSTONE_FERNET_REPO + '2'
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'Some key'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'Some other key'},
        }
        new_keys_map = action.rotate_keys(keys_map, 2)

        # Staged key should be the new key
        self.assertEqual('Some new key',
                         new_keys_map[staged_key_index]['content'])
        # primary key should be the previous staged key
        self.assertEqual('Some key',
                         new_keys_map[new_primary_key_index]['content'])

    def test_purge_excess_keys_should_purge(self):
        action = parameters.RotateFernetKeysAction()
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'key0'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'key1'},
            password_utils.KEYSTONE_FERNET_REPO + '2': {
                'content': 'key2'},
            password_utils.KEYSTONE_FERNET_REPO + '3': {
                'content': 'key3'},
            password_utils.KEYSTONE_FERNET_REPO + '4': {
                'content': 'key4'},
        }
        max_keys = 3
        keys_map = action.purge_excess_keys(max_keys, keys_map)
        self.assertEqual(max_keys, len(keys_map))
        # It should keep index 0, 3 and 4
        self.assertIn(password_utils.KEYSTONE_FERNET_REPO + '0', keys_map)
        self.assertIn(password_utils.KEYSTONE_FERNET_REPO + '3', keys_map)
        self.assertIn(password_utils.KEYSTONE_FERNET_REPO + '4', keys_map)
        # It sould have removed index 1 and 2
        self.assertNotIn(password_utils.KEYSTONE_FERNET_REPO + '1', keys_map)
        self.assertNotIn(password_utils.KEYSTONE_FERNET_REPO + '2', keys_map)

    def test_purge_excess_keys_should_not_purge_if_equal_to_max(self):
        action = parameters.RotateFernetKeysAction()
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'key0'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'key1'},
            password_utils.KEYSTONE_FERNET_REPO + '2': {
                'content': 'key2'},
        }
        max_keys = 3
        keys_map = action.purge_excess_keys(max_keys, keys_map)
        self.assertEqual(max_keys, len(keys_map))

    def test_purge_excess_keys_should_not_purge_if_less_than_max(self):
        action = parameters.RotateFernetKeysAction()
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'key0'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'key1'},
        }
        max_keys = 3
        keys_map = action.purge_excess_keys(max_keys, keys_map)
        self.assertEqual(2, len(keys_map))


class GetNetworkConfigActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_set')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
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
            "properties": {"config": "echo \'{\"network_config\": {}}\'"}
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

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_set')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
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
