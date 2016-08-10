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

import mock
import yaml

from tripleo_common.tests import base
from tripleo_common.utils import validations


VALIDATION_GROUP_1 = """---
- hosts: overcloud
  vars:
    metadata:
      name: First validation
      description: A validation belonging to group1
      groups:
        - group1
  tasks:
  - name: Ping the nodes
    ping:
"""

VALIDATION_WITH_METADATA = """---
- hosts: undercloud
  vars:
    metadata:
      name: Validation with metadata
      description: A validation with extra metadata
      foo: a foo metadata
      bar: 42
  tasks:
  - name: Do something useful
    watch_tv:
"""

VALIDATION_GROUPS_1_2 = """---
- hosts: undercloud
  vars:
    metadata:
      name: Validation from many groups
      description: A validation belonging to groups 1 and 2
      groups:
        - group1
        - group2
  tasks:
  - name: Do something useful
    watch_tv:
"""

VALIDATION_GROUP_1_PARSED = {
    'description': 'A validation belonging to group1',
    'groups': ['group1'],
    'id': 'VALIDATION_GROUP_1',
    'metadata': {},
    'name': 'First validation',
}

VALIDATION_WITH_METADATA_PARSED = {
    'description': 'A validation with extra metadata',
    'groups': [],
    'id': 'VALIDATION_WITH_METADATA',
    'metadata': {'foo': 'a foo metadata', 'bar': 42},
    'name': 'Validation with metadata',
}

VALIDATION_GROUPS_1_2_PARSED = {
    'description': 'A validation belonging to groups 1 and 2',
    'groups': ['group1', 'group2'],
    'id': 'VALIDATION_GROUPS_1_2',
    'metadata': {},
    'name': 'Validation from many groups',
}


class ValidationsKeyTest(base.TestCase):

    @mock.patch("oslo_concurrency.processutils.execute")
    def test_create_ssh_keypair(self, mock_execute):
        validations.create_ssh_keypair('/path/to/key')
        mock_execute.assert_called_once_with(
            '/usr/bin/ssh-keygen', '-t', 'rsa', '-N', '',
            '-f', '/path/to/key', '-C', 'tripleo-validations')


class LoadValidationsTest(base.TestCase):

    def test_get_validation_metadata(self):
        validation = yaml.safe_load(VALIDATION_GROUP_1)
        value = validations.get_validation_metadata(validation, 'name')
        self.assertEqual('First validation', value)

    @mock.patch('tripleo_common.utils.validations.DEFAULT_METADATA')
    def test_get_validation_metadata_default_value(self, mock_metadata):
        mock_metadata.get.return_value = 'default_value'
        value = validations.get_validation_metadata({}, 'missing')
        self.assertEqual('default_value', value)

    def test_get_remaining_metadata(self):
        validation = yaml.safe_load(VALIDATION_WITH_METADATA)
        value = validations.get_remaining_metadata(validation)
        expected = {
            'foo': 'a foo metadata',
            'bar': 42
        }
        self.assertEqual(expected, value)

    def test_get_remaining_metadata_no_extra(self):
        validation = yaml.safe_load(VALIDATION_GROUP_1)
        value = validations.get_remaining_metadata(validation)
        self.assertEqual({}, value)

    @mock.patch('glob.glob')
    def test_load_validations_no_group(self, mock_glob):
        mock_glob.return_value = ['VALIDATION_GROUP_1',
                                  'VALIDATION_WITH_METADATA']
        mock_open_context = mock.mock_open()
        mock_open_context().read.side_effect = [VALIDATION_GROUP_1,
                                                VALIDATION_WITH_METADATA]

        with mock.patch('tripleo_common.utils.validations.open',
                        mock_open_context):
            my_validations = validations.load_validations()

        expected = [VALIDATION_GROUP_1_PARSED, VALIDATION_WITH_METADATA_PARSED]
        self.assertEqual(expected, my_validations)

    @mock.patch('glob.glob')
    def test_load_validations_group(self, mock_glob):
        mock_glob.return_value = ['VALIDATION_GROUPS_1_2',
                                  'VALIDATION_GROUP_1',
                                  'VALIDATION_WITH_METADATA']
        mock_open_context = mock.mock_open()
        mock_open_context().read.side_effect = [VALIDATION_GROUPS_1_2,
                                                VALIDATION_GROUP_1,
                                                VALIDATION_WITH_METADATA]

        with mock.patch('tripleo_common.utils.validations.open',
                        mock_open_context):
            my_validations = validations.load_validations(groups=['group1'])

        expected = [VALIDATION_GROUPS_1_2_PARSED, VALIDATION_GROUP_1_PARSED]
        self.assertEqual(expected, my_validations)
