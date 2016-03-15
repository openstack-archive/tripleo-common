# Copyright 2015 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mock

from tripleo_common.tests import base
from tripleo_common import upgrade


class StackUpgradeManagerTest(base.TestCase):

    def setUp(self):
        super(StackUpgradeManagerTest, self).setUp()

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_upgrade(self, mock_template_contents, mock_env_files):
        heatclient = mock.MagicMock()
        heatclient.stacks.get.return_value = mock.MagicMock(
            stack_name='stack', id='stack_id')
        mock_template_contents.return_value = ({}, 'template body')
        mock_env_files.return_value = ({}, {})
        upgrade.StackUpgradeManager(
            heatclient=heatclient,
            stack_id='stack_id',
            tht_dir='/tmp/'
        ).upgrade()
        params = {
            'existing': True,
            'stack_id': 'stack_id',
            'template': 'template body',
            'files': {},
            'parameters': {},
            'environment': {
            },
            'timeout_mins': 240,
        }
        heatclient.stacks.update.assert_called_once_with(**params)
        mock_env_files.assert_called_once_with(env_paths=[
            '/tmp/environments/major-upgrade-pacemaker.yaml'])

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_upgrade_post(self, mock_template_contents, mock_env_files):
        heatclient = mock.MagicMock()
        heatclient.stacks.get.return_value = mock.MagicMock(
            stack_name='stack', id='stack_id')
        mock_template_contents.return_value = ({}, 'template body')
        mock_env_files.return_value = ({}, {})
        upgrade.StackUpgradeManager(
            heatclient=heatclient,
            stack_id='stack_id',
            tht_dir='/tmp/'
        ).upgrade_post()
        params = {
            'existing': True,
            'stack_id': 'stack_id',
            'template': 'template body',
            'files': {},
            'parameters': {},
            'environment': {
            },
            'timeout_mins': 240,
        }
        heatclient.stacks.update.assert_called_once_with(**params)
        mock_env_files.assert_called_once_with(env_paths=[
            '/tmp/environments/major-upgrade-pacemaker-converge.yaml'])

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_upgrade_pre(self, mock_template_contents, mock_env_files):
        heatclient = mock.MagicMock()
        heatclient.stacks.get.return_value = mock.MagicMock(
            stack_name='stack', id='stack_id')
        mock_template_contents.return_value = ({}, 'template body')
        mock_env_files.return_value = ({}, {})
        upgrade.StackUpgradeManager(
            heatclient=heatclient,
            stack_id='stack_id',
            tht_dir='/tmp/'
        ).upgrade_pre()
        params = {
            'existing': True,
            'stack_id': 'stack_id',
            'template': 'template body',
            'files': {},
            'parameters': {},
            'environment': {
            },
            'timeout_mins': 240,
        }
        heatclient.stacks.update.assert_called_once_with(**params)
        mock_env_files.assert_called_once_with(env_paths=[
            '/tmp/environments/major-upgrade-pacemaker-init.yaml'])
