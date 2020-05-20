# Copyright 2016 Red Hat, Inc.
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

from heatclient import exc as heat_exc
import six
from swiftclient import exceptions as swiftexceptions

from tripleo_common.tests import base
from tripleo_common.utils import overcloudrc


class OvercloudRcTest(base.TestCase):

    def test_generate_overcloudrc(self):

        stack = mock.MagicMock()
        stack.stack_name = 'overcast'
        stack.to_dict.return_value = {
            "outputs": [
                {'output_key': 'KeystoneURL',
                 'output_value': 'http://foo.com:8000/'},
                {'output_key': 'EndpointMap',
                 'output_value': {'KeystoneAdmin': {'host': 'fd00::1'}}},
            ]
        }

        result = overcloudrc._create_overcloudrc(stack, "foo", "AdminPassword",
                                                 "regionTwo")

        self.assertIn("export no_proxy='[fd00::1],foo,foo.com'",
                      result['overcloudrc'])
        self.assertIn("OS_PASSWORD=AdminPassword", result['overcloudrc'])

        self.assertIn("export PYTHONWARNINGS='ignore:Certificate",
                      result['overcloudrc'])
        self.assertIn("OS_IDENTITY_API_VERSION=3", result['overcloudrc'])
        self.assertIn(overcloudrc.CLOUDPROMPT, result['overcloudrc'])
        self.assertIn("OS_AUTH_TYPE=password", result['overcloudrc'])
        self.assertIn("OS_AUTH_URL=http://foo.com:8000/",
                      result['overcloudrc'])
        self.assertIn("OS_REGION_NAME=regionTwo",
                      result['overcloudrc'])

    def test_generate_overcloudrc_with_duplicated_no_proxy(self):

        stack = mock.MagicMock()
        stack.stack_name = 'overcast'
        stack.to_dict.return_value = {
            "outputs": [
                {'output_key': 'KeystoneURL',
                 'output_value': 'http://foo.com:8000/'},
                {'output_key': 'EndpointMap',
                 'output_value': {'KeystoneAdmin': {'host': 'fd00::1'}}},
            ]
        }

        result = overcloudrc._create_overcloudrc(
            stack, "foo,foo.com", "AdminPassword", "regionTwo")

        self.assertIn("export no_proxy='[fd00::1],foo,foo.com'",
                      result['overcloudrc'])
        self.assertIn("OS_PASSWORD=AdminPassword", result['overcloudrc'])

        self.assertIn("export PYTHONWARNINGS='ignore:Certificate",
                      result['overcloudrc'])
        self.assertIn("OS_IDENTITY_API_VERSION=3", result['overcloudrc'])
        self.assertIn(overcloudrc.CLOUDPROMPT, result['overcloudrc'])
        self.assertIn("OS_AUTH_TYPE=password", result['overcloudrc'])
        self.assertIn("OS_AUTH_URL=http://foo.com:8000/",
                      result['overcloudrc'])
        self.assertIn("OS_REGION_NAME=regionTwo",
                      result['overcloudrc'])

    def test_overcloudrc_no_stack(self):
        mock_swift = mock.MagicMock()
        mock_heat = mock.MagicMock()
        not_found = heat_exc.HTTPNotFound()
        mock_heat.stacks.get.side_effect = not_found
        ex = self.assertRaises(RuntimeError,
                               overcloudrc.create_overcloudrc,
                               mock_swift, mock_heat, "overcast")

        self.assertEqual((
            "The Heat stack overcast could not be found. Make sure you have "
            "deployed before calling this action."
        ), six.text_type(ex))

    def test_overcloudrc_no_env(self):
        mock_swift = mock.MagicMock()
        mock_heat = mock.MagicMock()
        mock_swift.get_object.side_effect = (
            swiftexceptions.ClientException("overcast"))
        ex = self.assertRaises(RuntimeError,
                               overcloudrc.create_overcloudrc,
                               mock_swift, mock_heat, "overcast")

        self.assertEqual("Error retrieving environment for plan overcast: "
                         "overcast", six.text_type(ex))

    def test_overcloudrc_no_password(self):
        mock_swift = mock.MagicMock()
        mock_heat = mock.MagicMock()
        mock_swift.get_object.return_value = (
            {}, "version: 1.0")
        ex = self.assertRaises(RuntimeError,
                               overcloudrc.create_overcloudrc,
                               mock_swift, mock_heat, "overcast")

        self.assertEqual(
            "Unable to find the AdminPassword in the plan environment.",
            six.text_type(ex))

    @mock.patch('tripleo_common.utils.overcloudrc._create_overcloudrc')
    def test_success(self, mock_create_overcloudrc):

        mock_env = """
        version: 1.0

        template: overcloud.yaml
        environments:
        - path: overcloud-resource-registry-puppet.yaml
        - path: environments/services/sahara.yaml
        parameter_defaults:
          BlockStorageCount: 42
          OvercloudControlFlavor: yummy
        passwords:
          AdminPassword: SUPERSECUREPASSWORD
        """
        mock_swift = mock.MagicMock()
        mock_heat = mock.MagicMock()
        mock_swift.get_object.return_value = ({}, mock_env)
        mock_create_overcloudrc.return_value = {
            "overcloudrc": "fake overcloudrc"
        }

        result = overcloudrc.create_overcloudrc(
            mock_swift, mock_heat, "overcast")
        self.assertEqual(result, {"overcloudrc": "fake overcloudrc"})
