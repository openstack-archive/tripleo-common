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
