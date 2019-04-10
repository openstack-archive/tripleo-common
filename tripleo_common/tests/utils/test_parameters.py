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

from tripleo_common import exception
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

    def test_swift_flavor_detected(self):
        compute_client = mock.MagicMock()

        # Mock for a compute_client.flavors.list result item and
        # compute_client.flavors.get
        flavor = mock.MagicMock()
        flavor.id = 1
        flavor.name = 'swift-storage'

        # Mock result of <flavor instance>.get_keys()
        flavor_keys = mock.MagicMock()
        flavor_keys.get.side_effect = ('swift-storage', )

        # Connecting the mock instances...
        flavor.get_keys.side_effect = (flavor_keys, )
        compute_client.flavors.list.side_effect = ((flavor, ),)
        compute_client.flavors.get.side_effect = (flavor, )

        # Calling `get_flavor` with an 'object-storage' role should return
        # the 'swift-storage' flavor.
        self.assertEqual(parameters.get_flavor('object-storage',
                                               compute_client),
                         'swift-storage')

    def test_compute_flavor_detected(self):
        compute_client = mock.MagicMock()

        # Mock for a compute_client.flavors.list result item and
        # compute_client.flavors.get
        flavor = mock.MagicMock()
        flavor.id = 1
        flavor.name = 'compute'

        # Mock result of <flavor instance>.get_keys()
        flavor_keys = mock.MagicMock()
        flavor_keys.get.side_effect = ('compute', )

        # Connecting the mock instances...
        flavor.get_keys.side_effect = (flavor_keys, )
        compute_client.flavors.list.side_effect = ((flavor, ),)
        compute_client.flavors.get.side_effect = (flavor, )

        # Calling `get_flavor` with a 'compute' role should return
        # the 'compute' flavor.
        self.assertEqual(parameters.get_flavor('compute', compute_client),
                         'compute')

    def test_profile_flavor_found(self):
        compute_client = mock.MagicMock()

        # Mock for a compute_client.flavors.find result item
        flavor = mock.MagicMock()
        flavor.id = 1
        flavor.name = 'oooq_compute'

        # Mock result of <flavor instance>.get_keys()
        flavor_keys = mock.MagicMock()
        flavor_keys.get.side_effect = ('compute', )

        # Connecting the mock instances...
        flavor.get_keys.side_effect = (flavor_keys, )
        compute_client.flavors.find.side_effect = (flavor, )

        # Calling `get_profile_of_flavor` with a 'oooq_compute' flavor
        # should return profile 'compute'.
        profile = parameters.get_profile_of_flavor('oooq_compute',
                                                   compute_client)
        self.assertEqual(profile, 'compute')

    def test_profile_flavor_not_found_exception(self):
        compute_client = mock.MagicMock()
        flavor = (Exception, )
        compute_client.flavors.find.side_effect = flavor

        # Calling `get_profile_of_flavor` with a 'oooq_compute' flavor
        # should raises DeriveParamsError exception
        self.assertRaises(exception.DeriveParamsError,
                          parameters.get_profile_of_flavor,
                          'oooq_compute', compute_client)

    def test_profile_flavor_not_found(self):
        compute_client = mock.MagicMock()
        compute_client.flavors.find.return_value = None

        # Calling `get_profile_of_flavor` with a 'oooq_compute' flavor
        # should raises DeriveParamsError exception
        self.assertRaises(exception.DeriveParamsError,
                          parameters.get_profile_of_flavor,
                          'oooq_compute', compute_client)

    def test_profile_not_found_flavor_found(self):
        compute_client = mock.MagicMock()

        # Mock for a compute_client.flavors.find result item
        flavor = mock.MagicMock()
        flavor.id = 1
        flavor.name = 'oooq_compute'

        # Mock result of <flavor instance>.get_keys()
        flavor_keys = mock.MagicMock()
        flavor_keys.get.side_effect = (exception.DeriveParamsError, )

        # Connecting the mock instances...
        flavor.get_keys.side_effect = (flavor_keys, )
        compute_client.flavors.find.side_effect = (flavor, )

        # Calling `get_profile_of_flavor` with a 'no_profile' flavor
        # should raises DeriveParamsError exception
        self.assertRaises(exception.DeriveParamsError,
                          parameters.get_profile_of_flavor,
                          'no_profile', compute_client)

    def test_convert_docker_params(self):

        env = {
            'parameter_defaults': {
                'DockerFooImage': 'bar',
                'DockerNoOverwriteImage': 'zzzz',
                'ContainerNoOverwriteImage': 'boom',
                'ContainerNoChangeImage': 'bar',
                'DockerNoChangeImage': 'bar',
            }
        }

        parameters.convert_docker_params(env)
        pd = env.get('parameter_defaults', {})
        self.assertEqual(pd['ContainerFooImage'], 'bar')
        self.assertEqual(pd['ContainerNoOverwriteImage'], 'boom')
        self.assertEqual(pd['ContainerNoChangeImage'], 'bar')
        self.assertEqual(pd['DockerNoChangeImage'], 'bar')
