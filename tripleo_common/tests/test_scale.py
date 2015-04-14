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

import collections
import mock

from tripleo_common import scale
from tripleo_common.tests import base


def mock_plan():
    plan = mock.Mock()
    plan.uuid = '5'
    plan.name = 'My Plan'
    plan.parameters = []
    plan.parameters.append({'name': 'compute-1::count', 'value': '2'})
    plan.to_dict.return_value = {
        'uuid': 5,
        'name': 'My Plan',
        'parameters': plan.parameters,
    }
    return plan


class ScaleManagerTest(base.TestCase):

    def setUp(self):
        super(ScaleManagerTest, self).setUp()
        self.image = collections.namedtuple('image', ['id'])
        self.heatclient = mock.MagicMock()
        self.tuskarclient = mock.MagicMock()
        self.tuskarclient.plans.patch.return_value = mock_plan()
        self.tuskarclient.plans.templates.return_value = {
            'plan.yaml': 'template body',
            'environment.yaml': 'resource_registry: {}\n',
        }

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.libutils.open', create=True)
    @mock.patch('tuskarclient.common.utils.find_resource')
    def test_scaleup(self, mock_find_resource, mock_open,
                     mock_template_contents, mock_env_files):
        mock_find_resource.return_value = mock_plan()
        mock_template_contents.return_value = ({}, 'template body')
        mock_env_files.return_value = ({}, {})
        manager = scale.ScaleManager(tuskarclient=self.tuskarclient,
                                     heatclient=self.heatclient,
                                     stack_id='stack',
                                     plan_id='plan')
        manager.scaleup(role='compute-1', num=3)
        self.tuskarclient.plans.patch.assert_called_once_with(
            '5', [{'name': 'compute-1::count', 'value': '3'}])
        self.heatclient.stacks.update.assert_called_once_with(
            stack_id='stack', template='template body', environment={},
            files={})

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.libutils.open', create=True)
    @mock.patch('tuskarclient.common.utils.find_resource')
    def test_invalid_scaleup(self, mock_find_resource, mock_open,
                             mock_template_contents, mock_env_files):
        mock_find_resource.return_value = mock_plan()
        manager = scale.ScaleManager(tuskarclient=self.tuskarclient,
                                     heatclient=self.heatclient,
                                     stack_id='stack',
                                     plan_id='plan')
        self.assertRaises(ValueError, manager.scaleup, 'compute-1', 1)
