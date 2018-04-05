# Copyright 2017 Red Hat, Inc.
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

from oslo_concurrency import processutils

from tripleo_common.actions import logging_to_swift
from tripleo_common.tests import base


class LogFormattingTest(base.TestCase):

    def test_log_formatting(self):
        messages = [
            {
                'body': {
                    'message': 'Test 1',
                    'level': 'INFO',
                    'timestamp': '1496322000000'
                }
            },
            {
                'body': {
                    'message': 'Test 2',
                    'level': 'WARN',
                    'timestamp': '1496329200000'
                }
            }
        ]
        action = logging_to_swift.FormatMessagesAction(messages)
        result = action.run({})
        self.assertEqual(result, ('2017-06-01 13:00:00 INFO Test 1\n'
                                  '2017-06-01 15:00:00 WARN Test 2'))


class PublishUILogToSwiftActionTest(base.TestCase):

    def setUp(self):
        super(PublishUILogToSwiftActionTest, self).setUp()
        self.container = 'container'
        self.swift = mock.MagicMock()
        swift_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_object_client',
            return_value=self.swift)
        swift_patcher.start()
        self.addCleanup(swift_patcher.stop)
        self.ctx = mock.MagicMock()

    def test_simple_success(self):
        self.swift.head_object.return_value = {
            'content-length': 1
        }
        self.swift.get_container.return_value = (
            {}, []
        )
        data = 'data'
        action = logging_to_swift.PublishUILogToSwiftAction(
            data, self.container)
        action.run(self.ctx)

        self.swift.get_object.assert_called_once()
        self.swift.head_object.assert_called_once()
        self.swift.put_object.assert_called_once()
        self.swift.get_container.assert_called_once()

    def test_rotate(self):
        self.swift.head_object.return_value = {
            'content-length': 2e7
        }
        self.swift.get_container.return_value = (
            {}, []
        )

        old_data = 'old data'
        new_data = 'new data'
        result = old_data + '\n' + new_data

        self.swift.get_object.return_value = ({}, old_data)

        action = logging_to_swift.PublishUILogToSwiftAction(
            new_data, self.container)
        action.run(self.ctx)

        self.swift.head_object.assert_called_once()
        self.swift.put_object.assert_called_with(
            self.container,
            'tripleo-ui.logs',
            result
        )


class PrepareLogDownloadActionTest(base.TestCase):

    def setUp(self):
        super(PrepareLogDownloadActionTest, self).setUp()
        self.log_files = (
            'tripleo-ui.logs.2',
            'tripleo-ui.logs.1',
            'tripleo-ui.logs'
        )
        self.swift = mock.MagicMock()
        self.swift.get_container.return_value = (
            {'x-container-meta-usage-tripleo': 'plan'}, [
                {'name': lf} for lf in self.log_files
            ]
        )
        self.swift.get_object.return_value = ({}, 'log content')
        swift_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_object_client',
            return_value=self.swift)
        swift_patcher.start()
        self.addCleanup(swift_patcher.stop)

        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_service')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run_success(self,
                         mock_create_tarball,
                         mock_get_obj_service):

        get_object_mock_calls = [
            mock.call('logging-container', lf) for lf in self.log_files
        ]
        get_container_mock_calls = [
            mock.call('logging-container')
        ]

        swift_service = mock.MagicMock()
        swift_service.delete.return_value = ([
            {'success': True},
        ])
        mock_get_obj_service.return_value = swift_service

        action = logging_to_swift.PrepareLogDownloadAction(
            'logging-container', 'downloads-container', 3600
        )

        action.run(self.ctx)

        self.swift.get_container.assert_has_calls(get_container_mock_calls)
        self.swift.get_object.assert_has_calls(
            get_object_mock_calls, any_order=True)
        mock_create_tarball.assert_called_once()

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_service')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run_error_creating_tarball(self,
                                        mock_create_tarball,
                                        mock_get_obj_service):

        mock_create_tarball.side_effect = processutils.ProcessExecutionError

        swift_service = mock.MagicMock()
        swift_service.delete.return_value = ([
            {'success': True},
        ])
        mock_get_obj_service.return_value = swift_service

        action = logging_to_swift.PrepareLogDownloadAction(
            'logging-container', 'downloads-container', 3600
        )

        result = action.run(self.ctx)

        error = "Error while creating a tarball"
        self.assertIn(error, result.error)
