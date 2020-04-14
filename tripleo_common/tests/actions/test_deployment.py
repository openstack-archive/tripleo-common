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
import json
import mock

from heatclient import exc as heat_exc
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import deployment
from tripleo_common.tests import base


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


class DeploymentStatusActionTest(base.TestCase):

    def setUp(self):
        super(DeploymentStatusActionTest, self).setUp()
        self.plan = 'overcloud'
        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_get_deployment_status(
            self, heat, mistral, swift):

        mock_stack = mock.Mock()
        mock_stack.stack_status = 'COMPLETE'
        heat().stacks.get.return_value = mock_stack

        body = 'deployment_status: DEPLOY_SUCCESS'
        swift().get_object.return_value = [mock.Mock(), body]

        execution = mock.Mock()
        execution.updated_at = 1
        execution.state = 'SUCCESS'
        execution.output = '{"deployment_status":"DEPLOY_SUCCESS"}'
        mistral().executions.get.return_value = execution
        mistral().executions.find.return_value = [execution]

        action = deployment.DeploymentStatusAction(self.plan)
        result = action.run(self.ctx)

        self.assertEqual(result['stack_status'], 'COMPLETE')
        self.assertEqual(result['deployment_status'], 'DEPLOY_SUCCESS')
        self.assertEqual(result['status_update'], None)

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_get_deployment_status_update_failed(
            self, heat, mistral, swift):

        mock_stack = mock.Mock()
        mock_stack.stack_status = 'FAILED'
        heat().stacks.get.return_value = mock_stack

        body = 'deployment_status: DEPLOY_SUCCESS'
        swift().get_object.return_value = [mock.Mock(), body]

        execution = mock.Mock()
        execution.updated_at = 1
        execution.state = 'SUCCESS'
        execution.output = '{"deployment_status":"DEPLOY_SUCCESS"}'
        mistral().executions.get.return_value = execution
        mistral().executions.find.return_value = [execution]

        action = deployment.DeploymentStatusAction(self.plan)
        result = action.run(self.ctx)

        self.assertEqual(result['stack_status'], 'FAILED')
        self.assertEqual(result['deployment_status'], 'DEPLOY_SUCCESS')
        self.assertEqual(result['status_update'], 'DEPLOY_FAILED')

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_get_deployment_status_update_deploying(
            self, heat, mistral, swift):

        mock_stack = mock.Mock()
        mock_stack.stack_status = 'IN_PROGRESS'
        heat().stacks.get.return_value = mock_stack

        body = 'deployment_status: DEPLOY_SUCCESS'
        swift().get_object.return_value = [mock.Mock(), body]

        execution = mock.Mock()
        execution.updated_at = 1
        execution.state = 'SUCCESS'
        execution.output = '{"deployment_status":"DEPLOY_SUCCESS"}'
        mistral().executions.get.return_value = execution
        mistral().executions.find.return_value = [execution]

        action = deployment.DeploymentStatusAction(self.plan)
        result = action.run(self.ctx)

        self.assertEqual(result['stack_status'], 'IN_PROGRESS')
        self.assertEqual(result['deployment_status'], 'DEPLOY_SUCCESS')
        self.assertEqual(result['status_update'], 'DEPLOYING')

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_get_deployment_status_update_success(
            self, heat, mistral, swift):

        mock_stack = mock.Mock()
        mock_stack.stack_status = 'COMPLETE'
        heat().stacks.get.return_value = mock_stack

        body = 'deployment_status: DEPLOYING'
        swift().get_object.return_value = [mock.Mock(), body]

        execution = mock.Mock()
        execution.updated_at = 1
        execution.state = 'SUCCESS'
        execution.output = '{"deployment_status":"DEPLOY_SUCCESS"}'
        mistral().executions.get.return_value = execution
        mistral().executions.find.return_value = [execution]

        action = deployment.DeploymentStatusAction(self.plan)
        result = action.run(self.ctx)

        self.assertEqual(result['stack_status'], 'COMPLETE')
        self.assertEqual(result['deployment_status'], 'DEPLOYING')

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_get_deployment_status_ansible_failed(
            self, heat, mistral, swift):

        mock_stack = mock.Mock()
        mock_stack.stack_status = 'COMPLETE'
        heat().stacks.get.return_value = mock_stack

        body = 'deployment_status: DEPLOYING'
        swift().get_object.return_value = [mock.Mock(), body]

        execution = mock.Mock()
        execution.updated_at = 1
        execution.state = 'SUCCESS'
        execution.output = '{"deployment_status":"DEPLOY_FAILED"}'
        mistral().executions.get.return_value = execution
        mistral().executions.find.return_value = [execution]

        action = deployment.DeploymentStatusAction(self.plan)
        result = action.run(self.ctx)

        self.assertEqual(result['stack_status'], 'COMPLETE')
        self.assertEqual(result['deployment_status'], 'DEPLOYING')

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_object_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_get_deployment_status_no_heat_stack(
            self, heat, mistral, swift):

        mock_stack = mock.Mock()
        mock_stack.stack_status = 'COMPLETE'
        heat().stacks.get.side_effect = heat_exc.HTTPNotFound()

        body = 'deployment_status: DEPLOY_SUCCESS'
        swift().get_object.return_value = [mock.Mock(), body]

        execution = mock.Mock()
        execution.updated_at = 1
        execution.state = 'SUCCESS'
        execution.output = '{"deployment_status":"DEPLOY_SUCCESS"}'
        mistral().executions.get.return_value = execution
        mistral().executions.find.return_value = [execution]

        action = deployment.DeploymentStatusAction(self.plan)
        result = action.run(self.ctx)

        self.assertEqual(result['status_update'], None)
        self.assertEqual(result['deployment_status'], None)


class DeploymentFailuresActionTest(base.TestCase):

    def setUp(self):
        super(DeploymentFailuresActionTest, self).setUp()
        self.plan = 'overcloud'
        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.actions.deployment.open')
    def test_get_deployment_failures(self, mock_open):

        test_result = dict(host0=["a", "b", "c"])
        mock_read = mock.MagicMock()
        mock_read.read.return_value = json.dumps(test_result)
        mock_open.return_value = mock_read

        action = deployment.DeploymentFailuresAction(self.plan)
        result = action.run(self.ctx)

        self.assertEqual(result['failures'], test_result)

    @mock.patch('tripleo_common.actions.deployment.open')
    def test_get_deployment_failures_no_file(self, mock_open):

        mock_open.side_effect = IOError()

        action = deployment.DeploymentFailuresAction(self.plan)
        result = action.run(self.ctx)

        self.assertTrue(result['message'].startswith(
                        "Ansible errors file not found at"))
        self.assertEqual({}, result['failures'])
