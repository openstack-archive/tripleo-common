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

from collections import namedtuple
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

    @mock.patch("oslo_concurrency.processutils.execute")
    @mock.patch('tempfile.mkstemp')
    def test_write_identity_file(self, mock_mkstemp, mock_execute):
        mock_open_context = mock.mock_open()
        mock_mkstemp.return_value = 'fd', 'tmp_path'
        with mock.patch('os.fdopen',
                        mock_open_context):
            validations.write_identity_file('private_key')

        mock_open_context.assert_called_once_with('fd', 'w')
        mock_open_context().write.assert_called_once_with('private_key')
        mock_execute.assert_called_once_with(
            '/usr/bin/sudo', '/usr/bin/chown', 'validations:', 'tmp_path')

    @mock.patch("oslo_concurrency.processutils.execute")
    def test_cleanup_identity_file(self, mock_execute):
        validations.cleanup_identity_file('/path/to/key')
        mock_execute.assert_called_once_with(
            '/usr/bin/sudo', '/usr/bin/rm', '-f', '/path/to/key')


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


class RunValidationTest(base.TestCase):

    @mock.patch('tripleo_common.utils.validations.find_validation')
    @mock.patch('oslo_concurrency.processutils.execute')
    @mock.patch('mistral.context.ctx')
    def test_run_validation(self, mock_ctx, mock_execute,
                            mock_find_validation):
        Ctx = namedtuple('Ctx', 'auth_uri user_name auth_token project_name')
        mock_ctx.return_value = Ctx(
            auth_uri='auth_uri',
            user_name='user_name',
            auth_token='auth_token',
            project_name='project_name'
        )
        mock_execute.return_value = 'output'
        mock_find_validation.return_value = 'validation_path'

        result = validations.run_validation('validation', 'identity_file',
                                            'plan')
        self.assertEqual('output', result)
        mock_execute.assert_called_once_with(
            '/usr/bin/sudo', '-u', 'validations',
            'OS_AUTH_URL=auth_uri',
            'OS_USERNAME=user_name',
            'OS_AUTH_TOKEN=auth_token',
            'OS_TENANT_NAME=project_name',
            '/usr/bin/run-validation',
            'validation_path',
            'identity_file',
            'plan'
        )
        mock_find_validation.assert_called_once_with('validation')
