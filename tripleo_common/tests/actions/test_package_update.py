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

from tripleo_common.actions import package_update
from tripleo_common.tests import base


class ClearBreakpointsActionTest(base.TestCase):

    def setUp(self,):
        super(ClearBreakpointsActionTest, self).setUp()
        self.stack_id = 'stack_id'
        self.refs = 'refs'

    @mock.patch('tripleo_common.actions.package_update.PackageUpdateManager')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    def test_run(self, mock_compute_client,
                 mock_orchestration_client,
                 mock_update_manager):
        action = package_update.ClearBreakpointsAction(self.stack_id,
                                                       self.refs)
        result = action.run()
        self.assertEqual(None, result)
        mock_compute_client.assert_called_once()
        mock_orchestration_client.assert_called_once()
        mock_update_manager.assert_called_once_with(
            mock_orchestration_client(),
            mock_compute_client(),
            self.stack_id,
            stack_fields={})
        mock_update_manager().clear_breakpoints.assert_called_once_with(
            self.refs)


class CancelStackUpdateActionTest(base.TestCase):

    def setUp(self,):
        super(CancelStackUpdateActionTest, self).setUp()
        self.stack_id = 'stack_id'

    @mock.patch('tripleo_common.actions.package_update.PackageUpdateManager')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    def test_run(self, mock_compute_client,
                 mock_orchestration_client,
                 mock_update_manager):
        action = package_update.CancelStackUpdateAction(self.stack_id)
        result = action.run()
        self.assertEqual(None, result)
        mock_compute_client.assert_called_once()
        mock_orchestration_client.assert_called_once()
        mock_update_manager.assert_called_once_with(
            mock_orchestration_client(),
            mock_compute_client(),
            self.stack_id,
            stack_fields={})
        mock_update_manager().cancel.assert_called_once()


class UpdateStackActionTest(base.TestCase):

    def setUp(self,):
        super(UpdateStackActionTest, self).setUp()
        self.timeout = 1
        self.container = 'container'

    @mock.patch('mistral.context.ctx')
    @mock.patch('tripleo_common.actions.templates.ProcessTemplatesAction.run')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    @mock.patch('tripleo_common.actions.package_update.time')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_run(self, mock_template_contents,
                 mock_time,
                 mock_compute_client,
                 mock_orchestration_client,
                 mock_workflow_client,
                 mock_templates_run,
                 mock_ctx,):
        mock_ctx.return_value = mock.MagicMock()
        heat = mock.MagicMock()
        heat.stacks.get.return_value = mock.MagicMock(
            stack_name='stack', id='stack_id')
        mock_orchestration_client.return_value = heat

        mock_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.variables = {
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'random_data': 'a_value'},
        }
        mock_mistral.environments.get.return_value = mock_env
        mock_workflow_client.return_value = mock_mistral

        # freeze time at datetime.datetime(2016, 9, 8, 16, 24, 24)
        mock_time.time.return_value = 1473366264

        mock_templates_run.return_value = {
            'StackAction': 'UPDATE',
            'DeployIdentifier': 1473366264,
            'UpdateIdentifier': 1473366264
        }

        action = package_update.UpdateStackAction(self.timeout,
                                                  container=self.container)
        action.run()

        # verify parameters are as expected
        expected_defaults = {
            'StackAction': 'UPDATE',
            'DeployIdentifier': 1473366264,
            'UpdateIdentifier': 1473366264,
            'random_data': 'a_value',
        }
        self.assertEqual(
            expected_defaults, mock_env.variables['parameter_defaults'])

        print(heat.mock_calls)
        heat.stacks.update.assert_called_once_with(
            'stack_id',
            StackAction='UPDATE',
            DeployIdentifier=1473366264,
            UpdateIdentifier=1473366264,
            existing='true',
            timeout_mins=1,
            environment={
                'resource_registry': {
                    'resources': {
                        '*': {
                            '*': {'UpdateDeployment': {'hooks': 'pre-update'}}
                        }
                    }
                }
            })
