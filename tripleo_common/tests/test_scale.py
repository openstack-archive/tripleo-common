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


def mock_stack():
    stack = mock.Mock()
    stack.name = 'My Stack'
    stack.parameters = {'ComputeCount': '2'}
    stack.to_dict.return_value = {
        'uuid': 5,
        'name': 'My Stack',
        'parameters': stack.parameters,
    }
    return stack


class ScaleManagerTest(base.TestCase):

    def setUp(self):
        super(ScaleManagerTest, self).setUp()
        self.image = collections.namedtuple('image', ['id'])
        self.heatclient = mock.MagicMock()
        self.heatclient.resources.list.return_value = [
            mock.MagicMock(
                links=[{'rel': 'stack',
                        'href': 'http://192.0.2.1:8004/v1/'
                                'a959ac7d6a4a475daf2428df315c41ef/'
                                'stacks/overcloud/123'}],
                logical_resource_id='logical_id',
                physical_resource_id='resource_id',
                resource_type='OS::Heat::ResourceGroup',
                resource_name='Compute'
            ),
            mock.MagicMock(
                links=[{'rel': 'stack',
                        'href': 'http://192.0.2.1:8004/v1/'
                                'a959ac7d6a4a475daf2428df315c41ef/'
                                'stacks/overcloud/124'}],
                logical_resource_id='node0',
                physical_resource_id='123',
                resource_type='OS::TripleO::Compute',
                parent_resource='Compute',
                resource_name='node0',
            )
        ]

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_scaledown(self, mock_get_template_contents, mock_env_files):
        mock_get_template_contents.return_value = ({}, 'template_body')
        mock_env_files.return_value = ({}, {})
        self.heatclient.stacks.get.return_value = mock_stack()
        manager = scale.ScaleManager(heatclient=self.heatclient,
                                     stack_id='stack', tht_dir='/tmp/')
        manager.scaledown(['resource_id'])
        env = {
            'resource_registry': {
                'resources': {'*': {'*': {'UpdateDeployment': {'hooks': []}}}}
            }
        }
        self.heatclient.stacks.update.assert_called_once_with(
            stack_id='stack',
            template='template_body',
            environment=env,
            existing=True,
            files={},
            timeout_mins=240,
            parameters={
                'ComputeCount': '0',
                'ComputeRemovalPolicies': [
                    {'resource_list': ['node0']}
                ]
            })

    def test_invalid_scaledown(self):
        manager = scale.ScaleManager(heatclient=self.heatclient,
                                     stack_id='stack')
        self.assertRaises(ValueError, manager.scaledown, 'invalid_resource_id')
