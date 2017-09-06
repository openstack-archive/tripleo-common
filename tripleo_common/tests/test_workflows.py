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

import os

import yaml

from tripleo_common.tests import base


WORKBOOK_DIRECTORY = os.path.join(os.path.dirname(__file__),
                                  '..', '..', 'workbooks')


class TestWorkflowStructure(base.TestCase):

    def setUp(self):
        self.workbooks = os.listdir(WORKBOOK_DIRECTORY)
        super(TestWorkflowStructure, self).setUp()

    def test_tags_are_set(self):
        for workbook in self.workbooks:
            full_path = os.path.join(WORKBOOK_DIRECTORY, workbook)
            with open(full_path) as f:
                wb_yaml = yaml.load(f)
            message = ("tripleo-common-managed tag is missing from a "
                       "workflow in {}").format(full_path)
            for wf_name, wf_spec in wb_yaml['workflows'].items():
                self.assertIn('tags', wf_spec, message)
                self.assertIn('tripleo-common-managed', wf_spec['tags'],
                              message)
