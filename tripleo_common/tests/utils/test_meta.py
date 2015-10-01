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
from tripleo_common.core import exception
from tripleo_common.tests import base
from tripleo_common.utils.meta import add_file_metadata


MAPPING_YAML_CONTENTS = """root_template: /path/to/overcloud.yaml
root_environment: /path/to/environment.yaml
topics:
  - title: Fake Single Environment Group Configuration
    description:
    environment_groups:
      - title:
        description: Random fake string of text
        environments:
          - file: /path/to/network-isolation.json
            title: Default Configuration
            description:

  - title: Fake Multiple Environment Group Configuration
    description:
    environment_groups:
      - title: Random Fake 1
        description: Random fake string of text
        environments:
          - file: /path/to/ceph-storage-env.yaml
            title: Fake1
            description: Random fake string of text

      - title: Random Fake 2
        description:
        environments:
          - file: /path/to/poc-custom-env.yaml
            title: Fake2
            description:
"""

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
        'meta': {'file-type': 'root-environment', 'enabled': 'True'},
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
    '/path/to/somefile.yaml': {'contents': "description: lorem ipsum"},
    'capabilities-map.yaml': {
        'contents': MAPPING_YAML_CONTENTS,
        'meta': {'file-type': 'capabilities-map'},
    },
}

PLAN_DATA_NO_META = {
    '/path/to/overcloud.yaml': {
        'contents': 'heat_template_version: 2015-04-30',
    },
    '/path/to/environment.yaml': {
        'contents': "parameters:\n"
                    "  one: uno\n"
                    "  obj:\n"
                    "    two: due\n"
                    "    three: tre\n",
    },
    '/path/to/network-isolation.json': {
        'contents': '{"parameters": {"one": "one"}}',
    },
    '/path/to/ceph-storage-env.yaml': {
        'contents': "parameters:\n"
                    "  obj:\n"
                    "    two: dos,\n"
                    "    three: three",
    },
    '/path/to/poc-custom-env.yaml': {
        'contents': "parameters:\n"
                    "  obj:\n"
                    "    two: two\n"
                    "  some::resource: /path/to/somefile.yaml",
    },
    '/path/to/somefile.yaml': {'contents': "description: lorem ipsum"},
    'capabilities-map.yaml': {
        'contents': MAPPING_YAML_CONTENTS,
        'meta': {'file-type': 'capabilities-map'},
    },
}


class UtilsMetaTest(base.TestCase):

    def test_add_file_metadata(self):
        # tests case where files have no metadata yet
        plan_files_with_metadata = add_file_metadata(PLAN_DATA_NO_META)
        self.assertEqual(
            PLAN_DATA,
            plan_files_with_metadata,
            "Metadata not added properly"
        )

        # tests case where files already have a metadata dict per file
        for k, v in PLAN_DATA.items():
            if 'meta' in v:
                v.update({'enabled': 'True'})
            else:
                v['meta'] = {'enabled': 'True'}

        for k, v in PLAN_DATA_NO_META.items():
            if 'meta' in v:
                v.update({'enabled': 'True'})
            else:
                v['meta'] = {'enabled': 'True'}

        plan_files_with_metadata = add_file_metadata(PLAN_DATA_NO_META)
        self.assertEqual(
            PLAN_DATA,
            plan_files_with_metadata,
            "Metadata not added properly"
        )

        # test to ensure having more than one capabilities-map file
        # results in an exception
        PLAN_DATA_NO_META.update({
            'capabilities-map2.yaml': {
                'contents': MAPPING_YAML_CONTENTS,
                'meta': {'file-type': 'capabilities-map'}
            }
        })
        self.assertRaises(exception.TooManyCapabilitiesMapFilesError,
                          add_file_metadata,
                          PLAN_DATA_NO_META)
