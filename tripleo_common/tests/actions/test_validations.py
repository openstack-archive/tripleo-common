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
import collections
import mock

from mistral_lib import actions
from oslo_concurrency.processutils import ProcessExecutionError

from tripleo_common.actions import validations
from tripleo_common import constants
from tripleo_common.tests import base
from tripleo_common.tests.utils import test_validations


class GetPubkeyActionTest(base.TestCase):

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_run_existing_pubkey(self, get_workflow_client_mock):
        mock_ctx = mock.MagicMock()
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        environment = collections.namedtuple('environment', ['variables'])
        mistral.environments.get.return_value = environment(variables={
            'public_key': 'existing_pubkey'
        })
        action = validations.GetPubkeyAction()
        self.assertEqual('existing_pubkey', action.run(mock_ctx))

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    @mock.patch('tripleo_common.utils.passwords.create_ssh_keypair')
    def test_run_no_pubkey(self, mock_create_keypair,
                           get_workflow_client_mock):
        mock_ctx = mock.MagicMock()
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        mistral.environments.get.side_effect = 'nope, sorry'
        mock_create_keypair.return_value = {
            'public_key': 'public_key',
            'private_key': 'private_key',
        }

        action = validations.GetPubkeyAction()
        self.assertEqual('public_key', action.run(mock_ctx))


class Enabled(base.TestCase):

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_validations_enabled(self, get_workflow_client_mock):
        mock_ctx = mock.MagicMock()
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        mistral.environments.get.return_value = {}
        action = validations.Enabled()
        result = action._validations_enabled(mock_ctx)
        self.assertEqual(result, True)

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_validations_disabled(self, get_workflow_client_mock):
        mock_ctx = mock.MagicMock()
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        mistral.environments.get.side_effect = Exception()
        action = validations.Enabled()
        result = action._validations_enabled(mock_ctx)
        self.assertEqual(result, False)

    @mock.patch(
        'tripleo_common.actions.validations.Enabled._validations_enabled')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_success_with_validations_enabled(self, get_workflow_client_mock,
                                              validations_enabled_mock):
        mock_ctx = mock.MagicMock()
        validations_enabled_mock.return_value = True
        action = validations.Enabled()
        action_result = action.run(mock_ctx)
        self.assertIsNone(action_result.error)
        self.assertEqual('Validations are enabled',
                         action_result.data['stdout'])

    @mock.patch(
        'tripleo_common.actions.validations.Enabled._validations_enabled')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_success_with_validations_disabled(self, get_workflow_client_mock,
                                               validations_enabled_mock):
        mock_ctx = mock.MagicMock()
        validations_enabled_mock.return_value = False
        action = validations.Enabled()
        action_result = action.run(mock_ctx)
        self.assertIsNone(action_result.data)
        self.assertEqual('Validations are disabled',
                         action_result.error['stdout'])


class ListValidationsActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.validations.load_validations')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_default(self, mock_get_object_client, mock_load_validations):
        mock_ctx = mock.MagicMock()
        swiftclient = mock.MagicMock(url='http://swift:8080/v1/AUTH_test')
        mock_get_object_client.return_value = swiftclient
        mock_load_validations.return_value = 'list of validations'

        action = validations.ListValidationsAction(plan='overcloud')
        self.assertEqual('list of validations', action.run(mock_ctx))
        mock_load_validations.assert_called_once_with(
            mock_get_object_client(), plan='overcloud', groups=None)

    @mock.patch('tripleo_common.utils.validations.load_validations')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_groups(self, mock_get_object_client, mock_load_validations):
        mock_ctx = mock.MagicMock()
        swiftclient = mock.MagicMock(url='http://swift:8080/v1/AUTH_test')
        mock_get_object_client.return_value = swiftclient
        mock_load_validations.return_value = 'list of validations'

        action = validations.ListValidationsAction(
            plan='overcloud', groups=['group1', 'group2'])
        self.assertEqual('list of validations', action.run(mock_ctx))
        mock_load_validations.assert_called_once_with(
            mock_get_object_client(), plan='overcloud',
            groups=['group1', 'group2'])


class ListGroupsActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.validations.load_validations')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, mock_get_object_client, mock_load_validations):
        mock_ctx = mock.MagicMock()
        swiftclient = mock.MagicMock(url='http://swift:8080/v1/AUTH_test')
        mock_get_object_client.return_value = swiftclient
        mock_load_validations.return_value = [
            test_validations.VALIDATION_GROUPS_1_2_PARSED,
            test_validations.VALIDATION_GROUP_1_PARSED,
            test_validations.VALIDATION_WITH_METADATA_PARSED]

        action = validations.ListGroupsAction(plan='overcloud')
        self.assertEqual({'group1', 'group2'}, action.run(mock_ctx))
        mock_load_validations.assert_called_once_with(
            mock_get_object_client(), plan='overcloud')


class RunValidationActionTest(base.TestCase):

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('tripleo_common.utils.validations.write_inputs_file')
    @mock.patch('tripleo_common.utils.validations.cleanup_inputs_file')
    @mock.patch('tripleo_common.utils.validations.write_identity_file')
    @mock.patch('tripleo_common.utils.validations.cleanup_identity_file')
    @mock.patch('tripleo_common.utils.validations.run_validation')
    def test_run(self, mock_run_validation,
                 mock_cleanup_identity_file,
                 mock_write_identity_file,
                 mock_cleanup_inputs_file,
                 mock_write_inputs_file,
                 mock_get_object_client,
                 get_workflow_client_mock):
        mock_ctx = mock.MagicMock()
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        environment = collections.namedtuple('environment', ['variables'])
        mistral.environments.get.return_value = environment(variables={
            'private_key': 'shhhh'
        })
        swiftclient = mock.MagicMock(url='http://swift:8080/v1/AUTH_test')
        mock_get_object_client.return_value = swiftclient
        mock_write_identity_file.return_value = 'identity_file_path'
        mock_write_inputs_file.return_value = 'inputs_file_path'
        mock_run_validation.return_value = 'output', 'error'
        action = validations.RunValidationAction('validation')
        expected = actions.Result(
            data={
                'stdout': 'output',
                'stderr': 'error'
            },
            error=None)
        self.assertEqual(expected, action.run(mock_ctx))
        mock_write_identity_file.assert_called_once_with('shhhh')
        mock_run_validation.assert_called_once_with(
            mock_get_object_client(),
            'validation',
            'identity_file_path',
            constants.DEFAULT_CONTAINER_NAME,
            'inputs_file_path',
            mock_ctx)
        mock_cleanup_identity_file.assert_called_once_with(
            'identity_file_path')
        mock_cleanup_inputs_file.assert_called_once_with('inputs_file_path')

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    @mock.patch('tripleo_common.utils.validations.write_inputs_file')
    @mock.patch('tripleo_common.utils.validations.cleanup_inputs_file')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('tripleo_common.utils.validations.write_identity_file')
    @mock.patch('tripleo_common.utils.validations.cleanup_identity_file')
    @mock.patch('tripleo_common.utils.validations.run_validation')
    def test_run_failing(self, mock_run_validation,
                         mock_cleanup_identity_file,
                         mock_write_identity_file,
                         mock_get_object_client,
                         mock_cleanup_inputs_file,
                         mock_write_inputs_file,
                         get_workflow_client_mock):
        mock_ctx = mock.MagicMock()
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        environment = collections.namedtuple('environment', ['variables'])
        mistral.environments.get.return_value = environment(variables={
            'private_key': 'shhhh'
        })
        swiftclient = mock.MagicMock(url='http://swift:8080/v1/AUTH_test')
        mock_get_object_client.return_value = swiftclient
        mock_write_identity_file.return_value = 'identity_file_path'
        mock_write_inputs_file.return_value = 'inputs_file_path'
        mock_run_validation.side_effect = ProcessExecutionError(
            stdout='output', stderr='error')
        action = validations.RunValidationAction('validation')
        expected = actions.Result(
            data=None,
            error={
                'stdout': 'output',
                'stderr': 'error'
            })
        self.assertEqual(expected, action.run(mock_ctx))
        mock_write_identity_file.assert_called_once_with('shhhh')
        mock_run_validation.assert_called_once_with(
            mock_get_object_client(),
            'validation',
            'identity_file_path',
            constants.DEFAULT_CONTAINER_NAME,
            'inputs_file_path',
            mock_ctx)
        mock_cleanup_identity_file.assert_called_once_with(
            'identity_file_path')
        mock_cleanup_inputs_file.assert_called_once_with('inputs_file_path')
