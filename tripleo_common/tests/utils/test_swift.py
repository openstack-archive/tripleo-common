# Copyright (c) 2017 Red Hat, Inc.
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

from swiftclient import exceptions as swiftexceptions

from tripleo_common.tests import base
from tripleo_common.utils import swift as swift_utils


class SwiftTest(base.TestCase):
    def setUp(self):
        super(SwiftTest, self).setUp()
        self.container_name = 'overcloud'
        self.swiftclient = mock.MagicMock()
        self.swiftclient.get_account.return_value = ({}, [
            {'name': self.container_name},
            {'name': 'test'},
        ])
        self.swiftclient.get_container.return_value = (
            {'x-container-meta-usage-tripleo': 'plan'}, [
                {'name': 'some-name.yaml'},
                {'name': 'some-other-name.yaml'},
                {'name': 'yet-some-other-name.yaml'},
                {'name': 'finally-another-name.yaml'}
            ]
        )

    def test_delete_container_success(self):
        swift_utils.empty_container(self.swiftclient, self.container_name)

        mock_calls = [
            mock.call('overcloud', 'some-name.yaml'),
            mock.call('overcloud', 'some-other-name.yaml'),
            mock.call('overcloud', 'yet-some-other-name.yaml'),
            mock.call('overcloud', 'finally-another-name.yaml')
        ]
        self.swiftclient.delete_object.assert_has_calls(
            mock_calls, any_order=True)

        self.swiftclient.get_account.assert_called()
        self.swiftclient.get_container.assert_called_with(self.container_name)

    def test_delete_container_not_found(self):
        self.assertRaises(ValueError,
                          swift_utils.empty_container,
                          self.swiftclient, 'idontexist')
        self.swiftclient.get_account.assert_called()
        self.swiftclient.get_container.assert_not_called()
        self.swiftclient.delete_object.assert_not_called()

    def test_delete_container_not_a_plan(self):
        self.swiftclient.get_container.return_value = (
            {'x-container-meta-usage-tripleo': 'not-a-plan'}, [
                {'name': 'some-name.yaml'},
                {'name': 'some-other-name.yaml'},
                {'name': 'yet-some-other-name.yaml'},
                {'name': 'finally-another-name.yaml'}
            ]
        )
        self.assertRaises(ValueError,
                          swift_utils.empty_container,
                          self.swiftclient, self.container_name)
        self.swiftclient.get_account.assert_called()
        self.swiftclient.get_container.assert_called()
        self.swiftclient.delete_object.assert_not_called()

    def test_get_or_create_container_create(self):
        self.swiftclient.get_container.side_effect = \
            swiftexceptions.ClientException('error')
        swift_utils.get_or_create_container(self.swiftclient, 'abc')
        self.swiftclient.put_container.assert_called()

    def test_get_or_create_container_get(self):
        swift_utils.get_or_create_container(self.swiftclient, 'abc')
        self.swiftclient.put_container.assert_not_called()
