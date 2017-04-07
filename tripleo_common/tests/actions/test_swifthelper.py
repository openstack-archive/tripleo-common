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
import mock

from mistral_lib import actions

from tripleo_common.actions import swifthelper
from tripleo_common.tests import base


class SwiftInformationActionTest(base.TestCase):

    def setUp(self):
        super(SwiftInformationActionTest, self).setUp()
        self.container_name = 'test'
        self.action = swifthelper.SwiftInformationAction(self.container_name)
        self.action.get_object_client = mock.Mock()

    def test_run_get_information(self):
        oc_mock = mock.MagicMock()
        oc_mock.head_container = mock.Mock()
        oc_mock.url = 'test_uri'
        mock_ctx = mock.Mock(auth_token='test_token')
        self.action.get_object_client.return_value = oc_mock

        return_data = {
            'container_url': 'test_uri/{}'.format(self.container_name),
            'auth_key': 'test_token'
        }
        return_obj = actions.Result(data=return_data, error=None)
        self.assertEqual(return_obj, self.action.run(mock_ctx))

        oc_mock.head_container.assert_called_with(self.container_name)

    def test_run_get_information_fails(self):
        oc_mock = mock.MagicMock()
        oc_mock.head_container = mock.Mock()
        mock_ctx = mock.MagicMock()
        fail = Exception('failure')
        oc_mock.head_container.side_effect = fail
        self.action.get_object_client.return_value = oc_mock

        return_obj = actions.Result(data=None, error='failure')

        self.assertEqual(return_obj, self.action.run(mock_ctx))


class SwiftTempUrlActionTest(base.TestCase):
    @mock.patch('time.time')
    @mock.patch('uuid.uuid4')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def _test_get_tempurl(self, secret, mock_get_object_client,
                          mock_uuid, mock_time):
        mock_ctx = mock.MagicMock()

        url = "http://swift:8080/v1/AUTH_test"
        swiftclient = mock.MagicMock(url=url)
        headers = {}
        if secret:
            headers['x-container-meta-temp-url-key'] = secret
        swiftclient.head_container.return_value = headers
        mock_get_object_client.return_value = swiftclient

        mock_uuid.return_value = '1-2-3-4'
        mock_time.return_value = 1500000000

        action = swifthelper.SwiftTempUrlAction("container", "obj")
        tempurl = action.run(mock_ctx)

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
