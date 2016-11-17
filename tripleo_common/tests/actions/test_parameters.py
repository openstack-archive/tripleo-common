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
    'GlancePassword': 'VqJYNEdKKsGZtgnHct77XBtrV',
    'RabbitPassword': 'ahuHRXdPMx9rzCdjD9CJJNCgA',
    'CephAdminKey': b'AQCQXtlXAAAAABAAT4Gk+U8EqqStL+JFa9bp1Q==',
    'HAProxyStatsPassword': 'P8tbdK6n4YUkTaUyy8XgEVTe6',
    'TrovePassword': 'V7A7zegkMdRFnYuN23gdc4KQC',
    'CeilometerPassword': 'RRdpwK6qf2pbKz2UtzxqauAdk',
    'GnocchiPassword': 'cRYHcUkMuJeK3vyU9pCaznUZc',
    'HeatStackDomainAdminPassword': 'GgTRyWzKYsxK4mReTJ4CM6sMc',
    'CephRgwKey': b'AQCQXtlXAAAAABAAUKcqUMu6oMjAXMjoUV4/3A==',
    'AodhPassword': '8VZXehsKc2HbmFFMKYuqxTJHn',
    'ManilaPassword': 'NYJN86Fua3X8AVFWmMhQa2zTH',
    'NeutronMetadataProxySharedSecret': 'Q2YgUCwmBkYdqsdhhCF4hbghu',
    'CephMonKey': b'AQCQXtlXAAAAABAA9l+59N3yH+C49Y0JiKeGFg==',
    'SwiftHashSuffix': 'td8mV6k7TYEGKCDvjVBwckpn9',
    'SnmpdReadonlyUserPassword': 'TestPassword',
    'SwiftPassword': 'z6EWAVfW7CuxvKdzjWTdrXCeg',
    'HeatPassword': 'bREnsXtMHKTHxt8XW6NXAYr48',
    'MysqlClustercheckPassword': 'jN4RMMWWJ4sycaRwh7UvrAtfX',
    'CephClientKey': b'AQCQXtlXAAAAABAAKyc+8St8i9onHyu2mPk+vg==',
    'NeutronPassword': 'ZxAjdU2UXCV4GM3WyPKrzAZXD'
}


class GetParametersActionTest(base.TestCase):

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
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
                '_get_workflow_client')
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
                '_get_workflow_client')
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
                '_get_baremetal_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_compute_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_workflow_client')
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
                '_get_orchestration_client')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_workflow_client', return_value="TestPassword")
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
                '_get_orchestration_client')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_run_passwords_exist(self, mock_ctx, mock_get_workflow_client,
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
            'passwords': _EXISTING_PASSWORDS
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
                '_get_orchestration_client')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_workflow_client')
    @mock.patch('mistral.context.ctx')
    def test_passwords_exist_in_heat(self, mock_ctx, mock_get_workflow_client,
                                     mock_get_snmpd_readonly_user_password,
                                     mock_get_orchestration_client):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"

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
            'passwords': existing_passwords
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
