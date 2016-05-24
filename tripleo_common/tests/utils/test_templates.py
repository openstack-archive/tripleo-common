# Copyright 2015 Red Hat, Inc.
# All Rights Reserved.
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

from tripleo_common.tests import base
from tripleo_common.utils import templates

PLAN_DATA = {
    '/path/to/overcloud.yaml': {
        'contents': 'heat_template_version: 2015-04-30',
        'meta': {'file-type': 'root-template'},
    },
    '/path/to/environment.yaml': {
        'contents': "parameters:\n"
                    "  one: uno\n"
                    "  obj:\n"
                    "    two: due\n"
                    "    three: tre\n",
        'meta': {
            'file-type': 'root-environment',
            'enabled': 'True'
        }
    },
    '/path/to/network-isolation.json': {
        'contents': '{"parameters": {"one": "one"}}',
        'meta': {'file-type': 'environment'},
    },
    '/path/to/ceph-storage-env.yaml': {
        'contents': "parameters:\n"
                    "  obj:\n"
                    "    two: dos,\n"
                    "    three: three",
        'meta': {'file-type': 'environment'},
    },
    '/path/to/poc-custom-env.yaml': {
        'contents': "parameters:\n"
                    "  obj:\n"
                    "    two: two\n"
                    "  some::resource: /path/to/somefile.yaml",
        'meta': {'file-type': 'environment'}
    },
    '/path/to/somefile.yaml': {'contents': "description: lorem ipsum"}
}


class UtilsTemplatesTest(base.TestCase):

    def setUp(self):
        super(UtilsTemplatesTest, self).setUp()

    @mock.patch("requests.request")
    def test_preprocess_templates(self, mock_request):

        # Setup
        envs = []
        mock_request.return_value = mock.Mock(content="""{
        "heat_template_version": "2016-04-08"
        }""")

        # Test a basic call to check the main code paths
        result = templates.preprocess_templates(
            "swift_base_url", "container", "template", envs, "auth_token")

        # Verify the values we get out
        self.assertEqual(result, {
            'environment': {},
            'files': {},
            'stack_name': 'container',
            'template': {
                'heat_template_version': '2016-04-08'
            }
        })
