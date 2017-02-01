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

from tripleo_common.actions import swifthelper
from tripleo_common.tests import base


class SwiftTempUrlActionTest(base.TestCase):
    @mock.patch('time.time')
    @mock.patch('uuid.uuid4')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('mistral.context.ctx')
    def _test_get_tempurl(self, secret, mock_ctx, mock_get_object_client,
                          mock_uuid, mock_time):
        mock_ctx.return_value = mock.MagicMock()

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
        tempurl = action.run()

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
