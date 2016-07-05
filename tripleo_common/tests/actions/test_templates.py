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

from tripleo_common.actions import templates
from tripleo_common import constants
from tripleo_common.tests import base


class UploadTemplatesActionTest(base.TestCase):

    @mock.patch('tempfile.NamedTemporaryFile')
    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    @mock.patch('tripleo_common.utils.tarball.'
                'tarball_extract_to_swift_container')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run(self, mock_create_tar, mock_extract_tar, mock_get_swift,
                 tempfile):

        tempfile.return_value.__enter__.return_value.name = "test"

        action = templates.UploadTemplatesAction(container='tar-container')
        action.run()

        mock_create_tar.assert_called_once_with(
            constants.DEFAULT_TEMPLATES_PATH, 'test')
        mock_extract_tar.assert_called_once_with(
            mock_get_swift.return_value, 'test', 'tar-container')


class ProcessTemplatesActionTest(base.TestCase):

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                '_get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    @mock.patch('mistral.context.ctx')
    def test_run(self, mock_ctx, mock_get_object_client,
                 mock_get_workflow_client, mock_get_template_contents,
                 mock_process_multiple_environments_and_files):

        mock_ctx.return_value = mock.MagicMock()
        mock_get_object_client.return_value = mock.MagicMock(
            url="http://test.com")

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

        # Test
        action = templates.ProcessTemplatesAction()
        result = action.run()

        # Verify the values we get out
        self.assertEqual(result, {
            'environment': {},
            'files': {},
            'stack_name': constants.DEFAULT_CONTAINER_NAME,
            'template': {
                'heat_template_version': '2016-04-30'
            }
        })
