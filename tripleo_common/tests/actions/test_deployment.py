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

from mistral.workflow import utils as mistral_workflow_utils

from tripleo_common.actions import deployment
from tripleo_common.tests import base


class OrchestrationDeployActionTest(base.TestCase):

    def setUp(self,):
        super(OrchestrationDeployActionTest, self).setUp()
        self.server_id = 'server_id'
        self.config = 'config'
        self.name = 'name'
        self.input_values = []
        self.action = 'CREATE'
        self.signal_transport = 'TEMP_URL_SIGNAL'
        self.timeout = 300
        self.group = 'script'

    def test_extract_container_object_from_swift_url(self):
        swift_url = 'https://example.com' + \
            '/v1/a422b2-91f3-2f46-74b7-d7c9e8958f5d30/container/object' + \
            '?temp_url_sig=da39a3ee5e6b4&temp_url_expires=1323479485'

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name,
                                                      self.timeout)
        self.assertEqual(('container', 'object'),
                         action._extract_container_object_from_swift_url(
                             swift_url))

    @mock.patch(
        'heatclient.common.deployment_utils.build_derived_config_params')
    def test_build_sc_params(self, build_derived_config_params_mock):
        build_derived_config_params_mock.return_value = 'built_params'
        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name)
        self.assertEqual('built_params', action._build_sc_params('swift_url'))
        build_derived_config_params_mock.assert_called_once()

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    def test_wait_for_data(self, get_obj_client_mock):
        swift = mock.MagicMock()
        swift.get_object.return_value = ({}, 'body')
        get_obj_client_mock.return_value = swift

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name)
        self.assertEqual('body', action._wait_for_data('container', 'object'))
        get_obj_client_mock.assert_called_once()
        swift.get_object.assert_called_once_with('container', 'object')

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    @mock.patch('time.sleep')
    def test_wait_for_data_timeout(self, sleep, get_obj_client_mock):
        swift = mock.MagicMock()
        swift.get_object.return_value = ({}, None)
        get_obj_client_mock.return_value = swift

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name,
                                                      timeout=10)
        self.assertEqual(None, action._wait_for_data('container', 'object'))
        get_obj_client_mock.assert_called_once()
        swift.get_object.assert_called_with('container', 'object')
        # Trying every 3 seconds, so 4 times for a timeout of 10 seconds
        self.assertEqual(swift.get_object.call_count, 4)

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_orchestration_client')
    @mock.patch('heatclient.common.deployment_utils.create_temp_url')
    @mock.patch('tripleo_common.actions.deployment.OrchestrationDeployAction.'
                '_extract_container_object_from_swift_url')
    @mock.patch('tripleo_common.actions.deployment.OrchestrationDeployAction.'
                '_build_sc_params')
    @mock.patch('tripleo_common.actions.deployment.OrchestrationDeployAction.'
                '_wait_for_data')
    def test_run(self, wait_for_data_mock, build_sc_params_mock,
                 extract_from_swift_url_mock, create_temp_url_mock,
                 get_heat_mock, get_obj_client_mock):
        extract_from_swift_url_mock.return_value = ('container', 'object')
        build_sc_params_mock.return_value = {'foo': 'bar'}
        config = mock.MagicMock()
        sd = mock.MagicMock()
        get_heat_mock().software_configs.create.return_value = config
        get_heat_mock().software_deployments.create.return_value = sd
        wait_for_data_mock.return_value = '{"deploy_status_code": 0}'

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name)
        expected = mistral_workflow_utils.Result(
            data={"deploy_status_code": 0},
            error=None)
        self.assertEqual(expected, action.run())
        create_temp_url_mock.assert_called_once()
        extract_from_swift_url_mock.assert_called_once()
        build_sc_params_mock.assert_called_once()
        get_obj_client_mock.assert_called_once()
        wait_for_data_mock.assert_called_once()

        sd.delete.assert_called_once()
        config.delete.assert_called_once()
        get_obj_client_mock.delete_object.called_once_with('container',
                                                           'object')
        get_obj_client_mock.delete_container.called_once_with('container')

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_orchestration_client')
    @mock.patch('heatclient.common.deployment_utils.create_temp_url')
    @mock.patch('tripleo_common.actions.deployment.OrchestrationDeployAction.'
                '_extract_container_object_from_swift_url')
    @mock.patch('tripleo_common.actions.deployment.OrchestrationDeployAction.'
                '_build_sc_params')
    @mock.patch('tripleo_common.actions.deployment.OrchestrationDeployAction.'
                '_wait_for_data')
    def test_run_timeout(self, wait_for_data_mock, build_sc_params_mock,
                         extract_from_swift_url_mock, create_temp_url_mock,
                         get_heat_mock, get_obj_client_mock):
        extract_from_swift_url_mock.return_value = ('container', 'object')
        config = mock.MagicMock()
        sd = mock.MagicMock()
        get_heat_mock().software_configs.create.return_value = config
        get_heat_mock().software_deployments.create.return_value = sd
        wait_for_data_mock.return_value = None

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name)
        expected = mistral_workflow_utils.Result(
            data={},
            error="Timeout for heat deployment 'name'")
        self.assertEqual(expected, action.run())

        sd.delete.assert_called_once()
        config.delete.assert_called_once()
        get_obj_client_mock.delete_object.called_once_with('container',
                                                           'object')
        get_obj_client_mock.delete_container.called_once_with('container')

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_orchestration_client')
    @mock.patch('heatclient.common.deployment_utils.create_temp_url')
    @mock.patch('tripleo_common.actions.deployment.OrchestrationDeployAction.'
                '_extract_container_object_from_swift_url')
    @mock.patch('tripleo_common.actions.deployment.OrchestrationDeployAction.'
                '_build_sc_params')
    @mock.patch('tripleo_common.actions.deployment.OrchestrationDeployAction.'
                '_wait_for_data')
    def test_run_failed(self, wait_for_data_mock, build_sc_params_mock,
                        extract_from_swift_url_mock, create_temp_url_mock,
                        get_heat_mock, get_obj_client_mock):
        extract_from_swift_url_mock.return_value = ('container', 'object')
        config = mock.MagicMock()
        sd = mock.MagicMock()
        get_heat_mock().software_configs.create.return_value = config
        get_heat_mock().software_deployments.create.return_value = sd
        wait_for_data_mock.return_value = '{"deploy_status_code": 1}'

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name)
        expected = mistral_workflow_utils.Result(
            data={"deploy_status_code": 1},
            error="Heat deployment failed for 'name'")
        self.assertEqual(expected, action.run())

        sd.delete.assert_called_once()
        config.delete.assert_called_once()
        get_obj_client_mock.delete_object.called_once_with('container',
                                                           'object')
        get_obj_client_mock.delete_container.called_once_with('container')
