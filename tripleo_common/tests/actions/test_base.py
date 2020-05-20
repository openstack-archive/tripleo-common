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

from unittest import mock

from ironicclient import client as ironicclient

from tripleo_common.actions import base
from tripleo_common.tests import base as tests_base
from tripleo_common.utils import keystone as keystone_utils


@mock.patch.object(keystone_utils, 'get_endpoint_for_project')
class TestActionsBase(tests_base.TestCase):

    def setUp(self):
        super(TestActionsBase, self).setUp()
        self.action = base.TripleOAction()

    @mock.patch.object(ironicclient, 'get_client', autospec=True)
    def test_get_baremetal_client(self, mock_client, mock_endpoint):
        mock_cxt = mock.MagicMock()
        mock_endpoint.return_value = mock.Mock(
            url='http://ironic/v1', region='ironic-region')
        self.action.get_baremetal_client(mock_cxt)
        mock_client.assert_called_once_with(
            1, endpoint='http://ironic/v1', max_retries=12,
            os_ironic_api_version='1.58', region_name='ironic-region',
            retry_interval=5, token=mock.ANY)
        mock_endpoint.assert_called_once_with(mock_cxt.security, 'ironic')
        mock_cxt.assert_not_called()
