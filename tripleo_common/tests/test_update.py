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
from tripleo_common import update


class UpdateManagerTest(base.TestCase):

    def setUp(self):
        super(UpdateManagerTest, self).setUp()

    @mock.patch('time.time')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.libutils.open', create=True)
    @mock.patch('tuskarclient.common.utils.find_resource')
    def test_update(self, mock_find_resource, mock_open,
                    mock_template_contents, mock_env_files, mock_time):
        heatclient = mock.MagicMock()
        novaclient = mock.MagicMock()
        tuskarclient = mock.MagicMock()
        mock_time.return_value = 123.5
        heatclient.stacks.get.return_value = mock.MagicMock(
            stack_name='stack', id='stack_id')
        mock_find_resource.return_value = mock.MagicMock(
            uuid='plan',
            parameters=[{'name': 'Compute-1::UpdateIdentifier', 'value': ''}])
        mock_template_contents.return_value = ({}, 'template body')
        mock_env_files.return_value = ({}, {})
        tuskarclient.plans.templates.return_value = {
            'plan.yaml': 'template body',
            'environment.yaml': 'resource_registry: {}\n',
        }
        update.PackageUpdateManager(
            heatclient=heatclient,
            novaclient=novaclient,
            stack_id='stack_id',
            tuskarclient=tuskarclient,
            plan_id='plan'
        ).update()
        params = {
            'existing': True,
            'stack_id': 'stack_id',
            'template': 'template body',
            'files': {},
            'parameters': {'Compute-1::UpdateIdentifier': '123'},
            'environment': {
                'resource_registry': {
                    'resources': {
                        '*': {
                            '*': {
                                'UpdateDeployment': {'hooks': 'pre-update'}
                            }
                        }
                    }
                }
            }
        }
        heatclient.stacks.update.assert_called_once_with(**params)
        mock_env_files.assert_called_once_with(env_paths=[])
