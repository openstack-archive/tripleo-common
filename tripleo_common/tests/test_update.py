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
    def test_update(self, mock_time):
        heatclient = mock.MagicMock()
        novaclient = mock.MagicMock()
        mock_time.return_value = 123.5
        heatclient.stacks.get.return_value = mock.MagicMock(
            stack_name='stack', id='stack_id')
        stack_fields = {
            'stack_id': 'stack_id',
            'stack_name': 'mystack',
            'template': 'template body',
            'environment': {},
            'files': {},
        }
        update.PackageUpdateManager(
            heatclient=heatclient,
            novaclient=novaclient,
            stack_id='stack_id',
            stack_fields=stack_fields,
        ).update()
        params = {
            'existing': True,
            'stack_name': 'mystack',
            'stack_id': 'stack_id',
            'template': 'template body',
            'files': {},
            'environment': {
                'resource_registry': {
                    'resources': {
                        '*': {
                            '*': {
                                'UpdateDeployment': {'hooks': 'pre-update'}
                            }
                        }
                    }
                },
                'parameter_defaults': {
                    'DeployIdentifier': 123,
                    'UpdateIdentifier': 123,
                    'StackAction': 'UPDATE'
                },
            },
            'timeout_mins': 240,
        }
        heatclient.stacks.update.assert_called_once_with(**params)
