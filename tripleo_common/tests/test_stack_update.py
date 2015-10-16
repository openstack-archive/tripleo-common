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

from tripleo_common import _stack_update
from tripleo_common.tests import base


class StackUpdateManagerTest(base.TestCase):

    def setUp(self):
        super(StackUpdateManagerTest, self).setUp()
        self.heatclient = mock.MagicMock()
        self.novaclient = mock.MagicMock()
        self.stack = mock.MagicMock(id='123', status='IN_PROGRESS',
                                    stack_name='stack')
        self.heatclient.stacks.get.return_value = self.stack

        server_mock = mock.MagicMock(id='instance_id')
        server_mock.name = 'instance_name'
        self.novaclient.servers.list.return_value = [server_mock]

        self.heatclient.software_deployments.get.return_value = \
            mock.MagicMock(server_id='instance_id')
        self.heatclient.resources.list.return_value = [
            mock.MagicMock(
                links=[{'rel': 'stack',
                        'href': 'http://192.0.2.1:8004/v1/'
                                'a959ac7d6a4a475daf2428df315c41ef/'
                                'stacks/overcloud/123'}],
                logical_resource_id='logical_id',
                physical_resource_id='resource_id'
            )
        ]

        def return_events(*args, **kwargs):
            if 'resource_name' in kwargs:
                return [
                    mock.MagicMock(
                        event_time='2015-03-25T09:15:04Z',
                        resource_name='Controller-0',
                        resource_status='CREATE_IN_PROGRESS',
                        resource_status_reason='UPDATE paused until Hook '
                                               'pre-update is cleared'),
                    mock.MagicMock(
                        event_time='2015-03-25T09:15:02Z',
                        resource_name='Controller-1',
                        resource_status='CREATE_COMPLETE',
                        resource_status_reason=''),
                ]
            else:
                return [
                    mock.MagicMock(
                        event_time='2015-03-25T09:14:02Z',
                        resource_status_reason='Stack UPDATE started')

                ]

        self.heatclient.events.list.side_effect = return_events
        self.stack_update_manager = _stack_update.StackUpdateManager(
            self.heatclient, self.novaclient, self.stack, 'pre-update')

    def test_get_status(self):
        status, resources = self.stack_update_manager.get_status()
        self.assertEqual('WAITING', status)

    def test_clear_breakpoints(self):
        good, bad = self.stack_update_manager.clear_breakpoints(
            ['resource_id'])
        self.heatclient.resources.signal.assert_called_once_with(
            stack_id='123',
            resource_name='logical_id',
            data={'unset_hook': 'pre-update'})
        self.assertEqual(good, ['resource_id'])
        self.assertEqual(bad, [])

    def test_clear_breakpoints_fails(self):
        self.heatclient.resources.signal.side_effect = Exception('error')
        good, bad = self.stack_update_manager.clear_breakpoints(
            ['resource_id'])
        self.assertEqual(good, [])
        self.assertEqual(bad, ['resource_id'])

    def test_cancel(self):
        self.stack_update_manager.cancel()
        self.heatclient.actions.cancel_update.assert_called_once_with('123')
        self.heatclient.resources.signal.assert_called_once_with(
            stack_id='123',
            resource_name='logical_id',
            data={'unset_hook': 'pre-update'})

    def test_intput_to_refs_regexp(self):
        result = self.stack_update_manager._input_to_refs(
            'instance_name.*', ['instance_id'])
        self.assertEqual(result, ['instance_id'])

    def test_intput_to_refs_invalid_regexp(self):
        result = self.stack_update_manager._input_to_refs(
            ']].*', ['instance_id'])
        self.assertEqual(result, [])
