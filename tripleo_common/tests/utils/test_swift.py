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

from unittest import mock

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

    def test_create_container(self):
        swift_utils.create_container(self.swiftclient, 'abc')
        self.swiftclient.put_container.assert_called()

    def test_get_object_string(self):
        self.swiftclient.get_object.return_value = (1, str('foo'))
        val = swift_utils.get_object_string(self.swiftclient, 'foo', 'bar')
        self.assertEqual(str('foo'), val)

    def test_get_object_string_from_bytes(self):
        self.swiftclient.get_object.return_value = (1, b'foo')
        val = swift_utils.get_object_string(self.swiftclient, 'foo', 'bar')
        self.assertEqual(str('foo'), val)

    def test_put_object_string(self):
        put_mock = mock.MagicMock()
        self.swiftclient.put_object = put_mock
        swift_utils.put_object_string(self.swiftclient, 'foo', 'bar',
                                      str('foo'))
        put_mock.assert_called_once_with('foo', 'bar', str('foo'))

    def test_put_object_string_from_bytes(self):
        put_mock = mock.MagicMock()
        self.swiftclient.put_object = put_mock
        swift_utils.put_object_string(self.swiftclient, 'foo', 'bar', b'foo')
        put_mock.assert_called_once_with('foo', 'bar', str('foo'))

    @mock.patch('time.time')
    @mock.patch('uuid.uuid4')
    def _test_get_tempurl(self, secret, mock_uuid, mock_time):
        url = "http://swift:8080/v1/AUTH_test"
        swiftclient = mock.MagicMock(url=url)
        headers = {}
        if secret:
            headers['x-container-meta-temp-url-key'] = secret
        swiftclient.head_container.return_value = headers

        mock_uuid.return_value = '1-2-3-4'
        mock_time.return_value = 1500000000

        tempurl = swift_utils.get_temp_url(swiftclient,
                                           "container", "obj")

        expected = "%s/container/obj?temp_url_sig=%s&temp_url_expires=%d" % (
            url, "ea8fdc57e2b2b1fbb7210bddd40029a7c8d5e2ed", 1500086400)
        self.assertEqual(expected, tempurl)

        if not secret:
            swiftclient.put_container.assert_called_with(
                'container', {'X-Container-Meta-Temp-Url-Key': '1-2-3-4'})

    def test_get_tempurl(self):
        # temp-url-key already set on the container
        self._test_get_tempurl('1-2-3-4')

    def test_get_tempurl_no_key(self):
        # temp-url-key not yet set
        self._test_get_tempurl(None)
