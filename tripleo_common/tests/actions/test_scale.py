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
import yaml

from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import scale
from tripleo_common import constants
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


class ScaleDownActionTest(base.TestCase):

    def setUp(self):
        super(ScaleDownActionTest, self).setUp()
        self.image = collections.namedtuple('image', ['id'])

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_delete')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, mock_get_object_client,
                 mock_get_template_contents, mock_env_files,
                 mock_get_heat_client, mock_cache):

        mock_env_files.return_value = ({}, {})
        heatclient = mock.MagicMock()
        heatclient.resources.list.return_value = [
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
        heatclient.stacks.get.return_value = mock_stack()
        mock_get_heat_client.return_value = heatclient

        mock_ctx = mock.MagicMock()
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': 'overcloud',
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )
        mock_get_object_client.return_value = swift

        env = {
            'resource_registry': {
                'resources': {'*': {'*': {'UpdateDeployment': {'hooks': []}}}}
            }
        }

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })

        # Test
        action = scale.ScaleDownAction(
            constants.STACK_TIMEOUT_DEFAULT, ['resource_id'], 'stack')
        action.run(mock_ctx)

        heatclient.stacks.update.assert_called_once_with(
            'stack',
            stack_name='stack',
            template={'heat_template_version': '2016-04-30'},
            environment=env,
            existing=True,
            files={},
            timeout_mins=240)

        mock_cache.assert_called_once_with(
            mock_ctx,
            "stack",
            "tripleo.parameters.get"
        )
