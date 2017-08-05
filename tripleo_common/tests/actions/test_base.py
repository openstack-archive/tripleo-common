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

import zlib

import mock

from ironicclient.v1 import client as ironicclient

from tripleo_common.actions import base
from tripleo_common.tests import base as tests_base
from tripleo_common.utils import keystone as keystone_utils

from swiftclient.exceptions import ClientException


@mock.patch.object(keystone_utils, 'get_endpoint_for_project')
class TestActionsBase(tests_base.TestCase):

    def setUp(self):
        super(TestActionsBase, self).setUp()
        self.action = base.TripleOAction()

    @mock.patch.object(ironicclient, 'Client')
    def test__get_baremetal_client(self, mock_client, mock_endpoint):
        mock_cxt = mock.MagicMock()
        mock_endpoint.return_value = mock.Mock(
            url='http://ironic/v1', region='ironic-region')
        self.action.get_baremetal_client(mock_cxt)
        mock_client.assert_called_once_with(
            'http://ironic/v1', max_retries=12, os_ironic_api_version='1.33',
            region_name='ironic-region', retry_interval=5, token=mock.ANY)
        mock_endpoint.assert_called_once_with(mock_cxt, 'ironic')
        mock_cxt.assert_not_called()

    def test_cache_key(self, mock_endpoint):
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"

        self.assertEqual(
            self.action._cache_key(container, key),
            cache_key
        )

    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_set(self, mock_conn, mock_endpoint):
        mock_ctx = mock.Mock()
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        cache_container = "__cache__"
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"
        compressed_json = zlib.compress("{\"foo\": 1}".encode())

        self.action.cache_set(mock_ctx, container, key, {"foo": 1})
        mock_swift.put_object.assert_called_once_with(
            cache_container,
            cache_key,
            compressed_json
        )
        mock_swift.delete_object.assert_not_called()

    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_set_none(self, mock_conn, mock_endpoint):
        mock_ctx = mock.Mock()
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        cache_container = "__cache__"
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"

        self.action.cache_set(mock_ctx, container, key, None)
        mock_swift.put_object.assert_not_called()
        mock_swift.delete_object.called_once_with(
            cache_container,
            cache_key
        )

    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_get_filled(self, mock_conn, mock_endpoint):
        mock_ctx = mock.Mock()
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        container = "TestContainer"
        key = "testkey"
        compressed_json = zlib.compress("{\"foo\": 1}".encode())
        # test if cache has something in it
        mock_swift.get_object.return_value = ([], compressed_json)
        result = self.action.cache_get(mock_ctx, container, key)
        self.assertEqual(result, {"foo": 1})

    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_empty(self, mock_conn, mock_endpoint):
        mock_ctx = mock.Mock()
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        cache_container = "__cache__"
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"

        mock_swift.get_object.side_effect = ClientException(
            "Foo"
        )
        result = self.action.cache_get(mock_ctx, container, key)
        self.assertFalse(result)

        # delete cache if we have a value
        self.action.cache_delete(mock_ctx, container, key)
        mock_swift.delete_object.assert_called_once_with(
            cache_container,
            cache_key
        )

    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_delete(self, mock_conn, mock_endpoint):
        mock_ctx = mock.Mock()
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        cache_container = "__cache__"
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"
        mock_swift.delete_object.side_effect = ClientException(
            "Foo"
        )
        self.action.cache_delete(mock_ctx, container, key)
        mock_swift.delete_object.assert_called_once_with(
            cache_container,
            cache_key
        )
