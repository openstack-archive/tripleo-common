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
from tripleo_common.tests import base
from tripleo_common.utils.templates import find_root_template
from tripleo_common.utils.templates import process_plan_data

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
        self.tpl, self.env, self.files = process_plan_data(PLAN_DATA)
        print(self.files)

    def test_find_root_template(self):
        # delete the root_template from sample data
        del PLAN_DATA['/path/to/overcloud.yaml']

        # without root, should return {}
        self.assertEqual({}, find_root_template(PLAN_DATA))

        # add root_template back to sample data
        root_template = {
            '/path/to/overcloud.yaml': {
                'contents': 'heat_template_version: 2015-04-30',
                'meta': {'file-type': 'root-template'}}
        }
        PLAN_DATA.update(root_template)

        self.assertEqual(root_template, find_root_template(PLAN_DATA))

    def test_template_found(self):
        self.assertEqual(self.tpl, 'heat_template_version: 2015-04-30')

    def test_files_found(self):
        self.assertEqual(self.files, {
            '/path/to/somefile.yaml': 'description: lorem ipsum',
        })
