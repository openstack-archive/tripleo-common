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

from tripleo_common.actions import validations
from tripleo_common.tests import base
from tripleo_common.tests.utils import test_validations


class GetPubkeyActionTest(base.TestCase):

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction._get_workflow_client')
    def test_run_existing_pubkey(self, get_workflow_client_mock):
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        environment = collections.namedtuple('environment', ['variables'])
        mistral.environments.get.return_value = environment(variables={
            'public_key': 'existing_pubkey'
        })
        action = validations.GetPubkeyAction()
        self.assertEqual('existing_pubkey', action.run())

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction._get_workflow_client')
    @mock.patch('tripleo_common.utils.validations.create_ssh_keypair')
    @mock.patch('tempfile.mkdtemp')
    @mock.patch('shutil.rmtree')
    def test_run_no_pubkey(self, mock_rmtree, mock_mkdtemp,
                           mock_create_keypair, get_workflow_client_mock):
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        mistral.environments.get.side_effect = 'nope, sorry'
        mock_mkdtemp.return_value = '/tmp_path'

        mock_open_context = mock.mock_open()
        mock_open_context().read.side_effect = ['private_key', 'public_key']

        with mock.patch('six.moves.builtins.open', mock_open_context):
            action = validations.GetPubkeyAction()
            self.assertEqual('public_key', action.run())

        mock_mkdtemp.assert_called_once()
        mock_create_keypair.assert_called_once_with('/tmp_path/id_rsa')
        mock_rmtree.asser_called_once_with('/tmp_path')


class ListValidationsActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.validations.load_validations')
    def test_run_default(self, mock_load_validations):
        mock_load_validations.return_value = 'list of validations'
        action = validations.ListValidationsAction()
        self.assertEqual('list of validations', action.run())
        mock_load_validations.assert_called_once_with(groups=None)

    @mock.patch('tripleo_common.utils.validations.load_validations')
    def test_run_groups(self, mock_load_validations):
        mock_load_validations.return_value = 'list of validations'
        action = validations.ListValidationsAction(groups=['group1',
                                                           'group2'])
        self.assertEqual('list of validations', action.run())
        mock_load_validations.assert_called_once_with(groups=['group1',
                                                              'group2'])


class ListGroupsActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.validations.load_validations')
    def test_run(self, mock_load_validations):
        mock_load_validations.return_value = [
            test_validations.VALIDATION_GROUPS_1_2_PARSED,
            test_validations.VALIDATION_GROUP_1_PARSED,
            test_validations.VALIDATION_WITH_METADATA_PARSED]
        action = validations.ListGroupsAction()
        self.assertEqual(set(['group1', 'group2']), action.run())
        mock_load_validations.assert_called_once_with()
