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

from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import parameters
from tripleo_common import constants
from tripleo_common.tests import base

_EXISTING_PASSWORDS = {
    'MistralPassword': 'VFJeqBKbatYhQm9jja67hufft',
    'BarbicanPassword': 'MGGQBtgKT7FnywvkcdMwE9nhx',
    'AdminPassword': 'jFmY8FTpvtF2e4d4ReXvmUP8k',
    'CeilometerMeteringSecret': 'CbHTGK4md4Cc8P8ZyzTns6wry',
    'ZaqarPassword': 'bbFgCTFbAH8vf9n3xvZCP8aMR',
    'NovaPassword': '7dZATgVPwD7Ergs9kTTDMCr7F',
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
    'KeystoneCredential0': 'ftJNQ_XlDUK7Lgvv1kdWf3SyqVsrvNDgoNV4kJg3yzw=',
    'KeystoneCredential1': 'c4MFq82TQLFLKpiiUjrKkp15dafE2ALcD3jbaIu3rfE=',
    'KeystoneFernetKey0': 'O8NSPxr4zXBBAoGIj-5aUmtE7-Jk5a4ptVsEhzJ8Vd8=',
    'KeystoneFernetKey1': 'AueoL37kd6eLjV29AG-Ruxu5szW47osgXx6aPOqtI6I=',
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
}


class GetParametersActionTest(base.TestCase):

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('mistral.context.ctx')
    def test_run(self, mock_ctx, mock_get_object_client,
                 mock_get_workflow_client, mock_get_orchestration_client,
                 mock_get_template_contents,
                 mock_process_multiple_environments_and_files):

        mock_ctx.return_value = mock.MagicMock()
        swift = mock.MagicMock(url="http://test.com")
        swift.get_object.side_effect = swiftexceptions.ClientException(
            'atest2')
        mock_get_object_client.return_value = swift

        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.variables = {
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }
        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_get_orchestration_client.return_value = mock_heat

        # Test
        action = parameters.GetParametersAction()
        action.run()
        mock_heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )


class ResetParametersActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_run(self, mock_ctx, mock_get_workflow_client):

        mock_ctx.return_value = mock.MagicMock()
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.name = constants.DEFAULT_CONTAINER_NAME
        mock_env.variables = {
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'SomeTestParameter': 42}
        }
        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        # Test
        action = parameters.ResetParametersAction()
        action.run()
        mock_mistral.environments.update.assert_called_once_with(
            name=constants.DEFAULT_CONTAINER_NAME,
            variables={
                'template': 'template',
                'environments': [{u'path': u'environments/test.yaml'}],
            }
        )


class UpdateParametersActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_run(self, mock_ctx, mock_get_workflow_client):

        mock_ctx.return_value = mock.MagicMock()
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.name = constants.DEFAULT_CONTAINER_NAME
        mock_env.variables = {
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }
        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        # Test
        test_parameters = {'SomeTestParameter': 42}
        action = parameters.UpdateParametersAction(test_parameters)
        action.run()

        mock_mistral.environments.update.assert_called_once_with(
            name=constants.DEFAULT_CONTAINER_NAME,
            variables={
                'temp_environment': 'temp_environment',
                'template': 'template',
                'environments': [{u'path': u'environments/test.yaml'}],
                'parameter_defaults': {'SomeTestParameter': 42}}
        )


class UpdateRoleParametersActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.parameters.set_count_and_flavor_params')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_baremetal_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_run(self, mock_ctx, mock_get_workflow_client,
                 mock_get_compute_client, mock_get_baremetal_client,
                 mock_set_count_and_flavor):

        mock_ctx.return_value = mock.MagicMock()
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.name = 'overcast'
        mock_env.variables = {}
        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        params = {'CephStorageCount': 1,
                  'OvercloudCephStorageFlavor': 'ceph-storage'}
        mock_set_count_and_flavor.return_value = params

        action = parameters.UpdateRoleParametersAction('ceph-storage',
                                                       'overcast')
        action.run()

        mock_mistral.environments.update.assert_called_once_with(
            name='overcast', variables={'parameter_defaults': params})


class GeneratePasswordsActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client', return_value="TestPassword")
    @mock.patch('mistral.context.ctx')
    def test_run(self, mock_ctx, mock_get_workflow_client,
                 mock_get_snmpd_readonly_user_password,
                 mock_get_orchestration_client):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"

        mock_ctx.return_value = mock.MagicMock()
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.name = constants.DEFAULT_CONTAINER_NAME
        mock_env.variables = {
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }
        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GeneratePasswordsAction()
        result = action.run()

        for password_param_name in constants.PASSWORD_PARAMETER_NAMES:
            self.assertTrue(password_param_name in result,
                            "%s is not in %s" % (password_param_name, result))

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_run_passwords_exist(self, mock_ctx, mock_get_workflow_client,
                                 mock_get_snmpd_readonly_user_password,
                                 mock_create_ssh_keypair,
                                 mock_get_orchestration_client):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}

        mock_ctx.return_value = mock.MagicMock()
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.name = constants.DEFAULT_CONTAINER_NAME
        mock_env.variables = {
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'passwords': _EXISTING_PASSWORDS.copy()
        }
        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GeneratePasswordsAction()
        result = action.run()

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_passwords_exist_in_heat(self, mock_ctx, mock_get_workflow_client,
                                     mock_get_snmpd_readonly_user_password,
                                     mock_create_ssh_keypair,
                                     mock_get_orchestration_client):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}

        existing_passwords = _EXISTING_PASSWORDS.copy()
        existing_passwords.pop("AdminPassword")

        mock_ctx.return_value = mock.MagicMock()
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.name = constants.DEFAULT_CONTAINER_NAME
        mock_env.variables = {
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'passwords': existing_passwords.copy()
        }
        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {
                'AdminPassword': 'ExistingPasswordInHeat',
            }
        }
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GeneratePasswordsAction()
        result = action.run()

        existing_passwords["AdminPassword"] = "ExistingPasswordInHeat"
        # ensure old passwords used and no new generation
        self.assertEqual(existing_passwords, result)


class GetPasswordsActionTest(base.TestCase):

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_password_from_parameter_defaults(self, mock_ctx,
                                              mock_get_workflow_client,
                                              mock_get_orchestration_client):

        mock_ctx.return_value = mock.MagicMock()
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.name = constants.DEFAULT_CONTAINER_NAME
        mock_env.variables = {
            "parameter_defaults": _EXISTING_PASSWORDS,
        }

        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        mock_orchestration = mock.MagicMock()
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GetPasswordsAction()
        result = action.run()

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_password_from_generated_passwords(self, mock_ctx,
                                               mock_get_workflow_client,
                                               mock_get_orchestration_client):

        mock_ctx.return_value = mock.MagicMock()
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.name = constants.DEFAULT_CONTAINER_NAME

        mock_env.variables = {
            "parameter_defaults": {},
            "passwords": _EXISTING_PASSWORDS,
        }

        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        mock_orchestration = mock.MagicMock()
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GetPasswordsAction()
        result = action.run()

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_password_merging_passwords(self, mock_ctx,
                                        mock_get_workflow_client,
                                        mock_get_orchestration_client):

        parameter_defaults = _EXISTING_PASSWORDS.copy()
        passwords = {"AdminPassword": parameter_defaults.pop("AdminPassword")}

        mock_ctx.return_value = mock.MagicMock()
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.name = constants.DEFAULT_CONTAINER_NAME
        mock_env.variables = {
            "parameter_defaults": parameter_defaults,
            "passwords": passwords
        }

        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        mock_orchestration = mock.MagicMock()
        mock_get_orchestration_client.return_value = mock_orchestration

        action = parameters.GetPasswordsAction()
        result = action.run()

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)


class GenerateFencingParametersActionTestCase(base.TestCase):

    @mock.patch('tripleo_common.utils.nodes.'
                'generate_hostmap')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_baremetal_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('mistral.context.ctx')
    def test_no_success(self, mock_ctx, mock_get_orchestration,
                        mock_get_workflow, mock_get_baremetal,
                        mock_get_compute, mock_generate_hostmap):
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
                                                            "test_action",
                                                            28,
                                                            5,
                                                            0,
                                                            True)

        result = action.run()["parameter_defaults"]

        self.assertTrue(result["EnableFencing"])
        self.assertEqual(len(result["FencingConfig"]["devices"]), 2)
        self.assertEqual(result["FencingConfig"]["devices"][0], {
                         "agent": "fence_ipmilan",
                         "host_mac": "00:11:22:33:44:55",
                         "params": {
                             "action": "test_action",
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
                             "action": "test_action",
                             "login": "test_os_username",
                             "passwd": "test_os_password",
                             "tenant_name": "test_os_tenant_name",
                             "pcmk_host_map": "compute_name_1:baremetal_name_1"
                             }
                         })
