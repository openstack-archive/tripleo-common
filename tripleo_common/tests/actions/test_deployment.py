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

from heatclient import exc as heat_exc
from mistral_lib import actions
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import deployment
from tripleo_common import constants
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

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_wait_for_data(self, get_obj_client_mock):
        mock_ctx = mock.MagicMock()

        swift = mock.MagicMock()
        swift.get_object.return_value = ({}, 'body')
        get_obj_client_mock.return_value = swift

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name)
        self.assertEqual('body', action._wait_for_data('container',
                                                       'object',
                                                       context=mock_ctx))
        get_obj_client_mock.assert_called_once()
        swift.get_object.assert_called_once_with('container', 'object')

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('time.sleep')
    def test_wait_for_data_timeout(self, sleep, get_obj_client_mock):
        mock_ctx = mock.MagicMock()
        swift = mock.MagicMock()
        swift.get_object.return_value = ({}, None)
        get_obj_client_mock.return_value = swift

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name,
                                                      timeout=10)
        self.assertIsNone(action._wait_for_data('container',
                                                'object',
                                                context=mock_ctx))
        get_obj_client_mock.assert_called_once()
        swift.get_object.assert_called_with('container', 'object')
        # Trying every 3 seconds, so 4 times for a timeout of 10 seconds
        self.assertEqual(swift.get_object.call_count, 4)

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
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
        mock_ctx = mock.MagicMock()
        build_sc_params_mock.return_value = {'foo': 'bar'}
        config = mock.MagicMock()
        sd = mock.MagicMock()
        get_heat_mock().software_configs.create.return_value = config
        get_heat_mock().software_deployments.create.return_value = sd
        wait_for_data_mock.return_value = '{"deploy_status_code": 0}'

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name)
        expected = actions.Result(
            data={"deploy_status_code": 0},
            error=None)
        self.assertEqual(expected, action.run(context=mock_ctx))
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

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
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
        mock_ctx = mock.MagicMock()
        config = mock.MagicMock()
        sd = mock.MagicMock()
        get_heat_mock().software_configs.create.return_value = config
        get_heat_mock().software_deployments.create.return_value = sd
        wait_for_data_mock.return_value = None

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name)
        expected = actions.Result(
            data={},
            error="Timeout for heat deployment 'name'")
        self.assertEqual(expected, action.run(mock_ctx))

        sd.delete.assert_called_once()
        config.delete.assert_called_once()
        get_obj_client_mock.delete_object.called_once_with('container',
                                                           'object')
        get_obj_client_mock.delete_container.called_once_with('container')

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
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
        mock_ctx = mock.MagicMock()
        config = mock.MagicMock()
        sd = mock.MagicMock()
        get_heat_mock().software_configs.create.return_value = config
        get_heat_mock().software_deployments.create.return_value = sd
        wait_for_data_mock.return_value = '{"deploy_status_code": 1}'

        action = deployment.OrchestrationDeployAction(self.server_id,
                                                      self.config, self.name)
        expected = actions.Result(
            data={"deploy_status_code": 1},
            error="Heat deployment failed for 'name'")
        self.assertEqual(expected, action.run(mock_ctx))

        sd.delete.assert_called_once()
        config.delete.assert_called_once()
        get_obj_client_mock.delete_object.called_once_with('container',
                                                           'object')
        get_obj_client_mock.delete_container.called_once_with('container')


class DeployStackActionTest(base.TestCase):

    def setUp(self,):
        super(DeployStackActionTest, self).setUp()

    @mock.patch('tripleo_common.actions.deployment.time')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_orchestration_client')
    def test_run(self, get_orchestration_client_mock,
                 mock_get_object_client, mock_get_template_contents,
                 mock_process_multiple_environments_and_files,
                 mock_time):

        mock_ctx = mock.MagicMock()
        # setup swift
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': 'overcloud',
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'random_existing_data': 'a_value'},
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )
        mock_get_object_client.return_value = swift

        heat = mock.MagicMock()
        heat.stacks.get.return_value = None
        get_orchestration_client_mock.return_value = heat

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        # freeze time at datetime.datetime(2016, 9, 8, 16, 24, 24)
        mock_time.time.return_value = 1473366264

        action = deployment.DeployStackAction(1, 'overcloud')
        action.run(mock_ctx)

        # verify parameters are as expected
        expected_defaults = {'DeployIdentifier': 1473366264,
                             'StackAction': 'CREATE',
                             'UpdateIdentifier': '',
                             'random_existing_data': 'a_value'}

        mock_env_updated = yaml.safe_dump({
            'name': 'overcloud',
            'temp_environment': 'temp_environment',
            'parameter_defaults': expected_defaults,
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_called_once_with(
            'overcloud',
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        heat.stacks.create.assert_called_once_with(
            environment={},
            files={},
            stack_name='overcloud',
            template={'heat_template_version': '2016-04-30'},
            timeout_mins=1,
        )
        swift.delete_object.assert_called_once_with(
            "overcloud-swift-rings", "swift-rings.tar.gz")
        swift.copy_object.assert_called_once_with(
            "overcloud-swift-rings", "swift-rings.tar.gz",
            "overcloud-swift-rings/swift-rings.tar.gz-%d" % 1473366264)

    @mock.patch('tripleo_common.actions.deployment.time')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_orchestration_client')
    def test_run_skip_deploy_identifier(
            self, get_orchestration_client_mock,
            mock_get_object_client, mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_time):

        mock_ctx = mock.MagicMock()
        # setup swift
        swift = mock.MagicMock(url="http://test.com")
        mock_get_object_client.return_value = swift

        heat = mock.MagicMock()
        heat.stacks.get.return_value = None
        get_orchestration_client_mock.return_value = heat

        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'random_existing_data': 'a_value'},
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        # freeze time at datetime.datetime(2016, 9, 8, 16, 24, 24)
        mock_time.time.return_value = 1473366264

        action = deployment.DeployStackAction(1, 'overcloud',
                                              skip_deploy_identifier=True)
        action.run(mock_ctx)

        # verify parameters are as expected
        mock_env_updated = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'parameter_defaults': {'StackAction': 'CREATE',
                                   'UpdateIdentifier': '',
                                   'random_existing_data': 'a_value'},
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_called_once_with(
            constants.DEFAULT_CONTAINER_NAME,
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        heat.stacks.create.assert_called_once_with(
            environment={},
            files={},
            stack_name='overcloud',
            template={'heat_template_version': '2016-04-30'},
            timeout_mins=1,
        )
        swift.delete_object.assert_called_once_with(
            "overcloud-swift-rings", "swift-rings.tar.gz")
        swift.copy_object.assert_called_once_with(
            "overcloud-swift-rings", "swift-rings.tar.gz",
            "overcloud-swift-rings/swift-rings.tar.gz-%d" % 1473366264)


class OvercloudRcActionTestCase(base.TestCase):
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_no_stack(self, mock_get_orchestration, mock_get_object):

        mock_ctx = mock.MagicMock()

        not_found = heat_exc.HTTPNotFound()
        mock_get_orchestration.return_value.stacks.get.side_effect = not_found

        action = deployment.OvercloudRcAction("overcast")
        result = action.run(mock_ctx)

        self.assertEqual(result.error, (
            "The Heat stack overcast could not be found. Make sure you have "
            "deployed before calling this action."
        ))

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_no_env(self, mock_get_orchestration, mock_get_object):

        mock_ctx = mock.MagicMock()

        mock_get_object.return_value.get_object.side_effect = (
            swiftexceptions.ClientException("overcast"))

        action = deployment.OvercloudRcAction("overcast")
        result = action.run(mock_ctx)
        self.assertEqual(result.error, "Error retrieving environment for plan "
                                       "overcast: overcast")

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_no_password(self, mock_get_orchestration, mock_get_object):
        mock_ctx = mock.MagicMock()

        mock_get_object.return_value.get_object.return_value = (
            {}, "version: 1.0")

        action = deployment.OvercloudRcAction("overcast")
        result = action.run(mock_ctx)

        self.assertEqual(
            result.error,
            "Unable to find the AdminPassword in the plan environment.")

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.utils.overcloudrc.create_overcloudrc')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_success(self, mock_get_orchestration, mock_create_overcloudrc,
                     mock_get_object):
        mock_ctx = mock.MagicMock()

        mock_env = """
        version: 1.0

        template: overcloud.yaml
        environments:
        - path: overcloud-resource-registry-puppet.yaml
        - path: environments/services/sahara.yaml
        parameter_defaults:
          BlockStorageCount: 42
          OvercloudControlFlavor: yummy
        passwords:
          AdminPassword: SUPERSECUREPASSWORD
        """
        mock_get_object.return_value.get_object.return_value = ({}, mock_env)
        mock_create_overcloudrc.return_value = {
            "overcloudrc": "fake overcloudrc"
        }

        action = deployment.OvercloudRcAction("overcast")
        result = action.run(mock_ctx)

        self.assertEqual(result, {"overcloudrc": "fake overcloudrc"})
