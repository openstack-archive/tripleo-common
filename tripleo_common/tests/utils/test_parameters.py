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

from tripleo_common.tests import base
from tripleo_common.utils import parameters


class ParametersTest(base.TestCase):

    @mock.patch('tripleo_common.utils.parameters.get_node_count')
    @mock.patch('tripleo_common.utils.parameters.get_flavor')
    def test_set_count_and_flavor_params_for_controller(self,
                                                        mock_get_flavor,
                                                        mock_get_node_count):
        mock_get_node_count.return_value = 1
        mock_get_flavor.return_value = 'control'
        expected = {
            'ControllerCount': 1,
            'OvercloudControlFlavor': 'control'
        }
        params = parameters.set_count_and_flavor_params('control', 1, 1)
        self.assertEqual(expected, params)

    @mock.patch('tripleo_common.utils.parameters.get_node_count')
    @mock.patch('tripleo_common.utils.parameters.get_flavor')
    def test_set_count_and_flavor_params_for_swift(self,
                                                   mock_get_flavor,
                                                   mock_get_node_count):
        mock_get_node_count.return_value = 1
        mock_get_flavor.return_value = 'swift-storage'
        expected = {
            'ObjectStorageCount': 1,
            'OvercloudSwiftStorageFlavor': 'swift-storage'
        }
        params = parameters.set_count_and_flavor_params('object-storage', 1, 1)
        self.assertEqual(expected, params)

    @mock.patch('tripleo_common.utils.parameters.get_node_count')
    @mock.patch('tripleo_common.utils.parameters.get_flavor')
    def test_set_count_and_flavor_params_for_role(self,
                                                  mock_get_flavor,
                                                  mock_get_node_count):
        mock_get_node_count.return_value = 1
        mock_get_flavor.return_value = 'ceph-storage'
        expected = {
            'CephStorageCount': 1,
            'OvercloudCephStorageFlavor': 'ceph-storage'
        }
        params = parameters.set_count_and_flavor_params('ceph-storage', 1, 1)
        self.assertEqual(expected, params)

    @mock.patch('tripleo_common.utils.parameters.get_node_count')
    @mock.patch('tripleo_common.utils.parameters.get_flavor')
    def test_set_count_and_flavor_params_for_custom_role(self,
                                                         mock_get_flavor,
                                                         mock_get_node_count):
        mock_get_node_count.return_value = 1
        mock_get_flavor.return_value = 'custom-role'
        expected = {
            'MyCustomRoleCount': 1,
            'OvercloudMyCustomRoleFlavor': 'custom-role'
        }
        params = parameters.set_count_and_flavor_params('my-custom-role', 1, 1)
        self.assertEqual(expected, params)
