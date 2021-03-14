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
