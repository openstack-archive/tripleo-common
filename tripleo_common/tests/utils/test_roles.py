#   Copyright 2017 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#

from unittest import mock

import yaml

from tripleo_common.exception import NotFound
from tripleo_common.exception import RoleMetadataError
from tripleo_common.tests import base
from tripleo_common.utils import roles as rolesutils

SAMPLE_ROLE = """
###############################################################################
# Role: sample                                                                #
###############################################################################
- name: sample
  description: |
    Sample!
  networks:
    - InternalApi
  HostnameFormatDefault: '%stackname%-sample-%index%'
  ServicesDefault:
    - OS::TripleO::Services::Timesync
"""
SAMPLE_ROLE_NETWORK_DICT = """
###############################################################################
# Role: sample                                                                #
###############################################################################
- name: sample
  description: |
    Sample!
  networks:
    InternalApi:
      subnet: internal_api_subnet
  HostnameFormatDefault: '%stackname%-sample-%index%'
  ServicesDefault:
    - OS::TripleO::Services::Timesync
"""
SAMPLE_GENERATED_ROLE = """
###############################################################################
# Role: sample                                                                #
###############################################################################
- name: sampleA
  description: |
    Sample!
  networks:
    - InternalApi
  HostnameFormatDefault: '%stackname%-sample-%index%'
  ServicesDefault:
    - OS::TripleO::Services::Timesync
"""
SAMPLE_ROLE_OBJ = {
    'HostnameFormatDefault': '%stackname%-sample-%index%',
    'ServicesDefault': ['OS::TripleO::Services::Timesync'],
    'description': 'Sample!\n',
    'name': 'sample',
    'networks': ['InternalApi']
}
SAMPLE_ROLE_OBJ_NETWORK_DICT = {
    'HostnameFormatDefault': '%stackname%-sample-%index%',
    'ServicesDefault': ['OS::TripleO::Services::Timesync'],
    'description': 'Sample!\n',
    'name': 'sample',
    'networks': {
        'InternalApi': {
            'subnet': 'internal_api_subnet'}
    }
}

ROLES_DATA_YAML_CONTENTS = """
- name: MyController
  CountDefault: 1
  ServicesDefault:
    - OS::TripleO::Services::CACerts

- name: Compute
  HostnameFormatDefault: '%stackname%-novacompute-%index%'
  ServicesDefault:
    - OS::TripleO::Services::NovaCompute
    - OS::TripleO::Services::DummyService

- name: CustomRole
  ServicesDefault:
    - OS::TripleO::Services::Kernel
"""


class TestRolesUtils(base.TestCase):
    @mock.patch('os.listdir')
    @mock.patch('os.path.exists')
    def test_get_roles_from_directory(self, exists_mock, listdir_mock):
        exists_mock.return_value = True
        listdir_mock.return_value = ['b.yaml', 'a.yaml']
        self.assertEqual(rolesutils.get_roles_list_from_directory('/foo'),
                         ['a', 'b'])

    @mock.patch('os.listdir')
    @mock.patch('os.path.exists')
    def test_get_roles_from_directory_failure(self, exists_mock, listdir_mock):
        exists_mock.return_value = False
        self.assertRaises(ValueError, rolesutils.get_roles_list_from_directory,
                          ['/foo'])

    def test_validate_roles(self):
        available_roles = ['a', 'b', 'c']
        requested_roles = ['b', 'c']
        try:
            rolesutils.check_role_exists(available_roles, requested_roles)
        except Exception:
            self.fail('Exception raised')

    def test_validate_roles_with_invalid_role(self):
        available_roles = ['a', 'b', 'c']
        requested_roles = ['b', 'd']
        self.assertRaises(NotFound, rolesutils.check_role_exists,
                          available_roles, requested_roles)

    @mock.patch('tripleo_common.utils.roles.check_role_exists')
    @mock.patch('tripleo_common.utils.roles.get_roles_list_from_directory')
    def test_generate_roles_data_from_directory(self, get_roles_mock,
                                                check_mock):
        get_roles_mock.return_value = ['foo', 'bar', 'baz']
        m = mock.mock_open(read_data=SAMPLE_ROLE)
        with mock.patch('tripleo_common.utils.roles.open', m) as open_mock:
            r = rolesutils.generate_roles_data_from_directory('/foo',
                                                              ['foo', 'bar'])
            open_mock.assert_any_call('/foo/foo.yaml', 'r')
            open_mock.assert_any_call('/foo/bar.yaml', 'r')

        header = '\n'.join(["#" * 79,
                            "# File generated by TripleO",
                            "#" * 79,
                            ""])
        expected = header + SAMPLE_ROLE * 2
        self.assertEqual(expected, r)
        get_roles_mock.assert_called_with('/foo')
        check_mock.assert_called_with(['foo', 'bar', 'baz'], ['foo', 'bar'])

    def test_validate_role_yaml(self):
        role = rolesutils.validate_role_yaml(SAMPLE_ROLE)
        self.assertEqual(SAMPLE_ROLE_OBJ, role)

    def test_validate_role_with_network_dict(self):
        role = rolesutils.validate_role_yaml(SAMPLE_ROLE_NETWORK_DICT)
        self.assertEqual(SAMPLE_ROLE_OBJ_NETWORK_DICT, role)

    def test_validate_role_yaml_with_file(self):
        m = mock.mock_open(read_data=SAMPLE_ROLE)
        with mock.patch('tripleo_common.utils.roles.open', m):
            r = rolesutils.validate_role_yaml(role_path='/foo.yaml')
        self.assertEqual(SAMPLE_ROLE_OBJ, r)

    def test_validate_role_yaml_invalid_params(self):
        self.assertRaises(ValueError, rolesutils.validate_role_yaml, 'foo',
                          'bar')

    def test_validate_role_yaml_missing_name(self):
        role = yaml.safe_load(SAMPLE_ROLE)
        del role[0]['name']
        self.assertRaises(RoleMetadataError, rolesutils.validate_role_yaml,
                          yaml.safe_dump(role))

    def test_validate_role_yaml_invalid_type(self):
        role = yaml.safe_load(SAMPLE_ROLE)
        role[0]['CountDefault'] = 'should not be a string'
        self.assertRaises(RoleMetadataError, rolesutils.validate_role_yaml,
                          yaml.safe_dump(role))

    def test_validate_role_yaml_invalid_network_type(self):
        role = yaml.safe_load(SAMPLE_ROLE)
        role[0]['networks'] = 'should not be a string'
        self.assertRaises(RoleMetadataError, rolesutils.validate_role_yaml,
                          yaml.safe_dump(role))

    @mock.patch('tripleo_common.utils.roles.check_role_exists')
    @mock.patch('tripleo_common.utils.roles.get_roles_list_from_directory')
    def test_generate_roles_with_one_role_generated(self, get_roles_mock,
                                                    check_mock):
        get_roles_mock.return_value = ['sample', 'bar', 'baz']
        m = mock.mock_open(read_data=SAMPLE_ROLE)
        with mock.patch('tripleo_common.utils.roles.open', m) as open_mock:
            r = rolesutils.generate_roles_data_from_directory(
                '/roles', ['sample:sampleA'])
            open_mock.assert_any_call('/roles/sample.yaml', 'r')

        header = '\n'.join(["#" * 79,
                            "# File generated by TripleO",
                            "#" * 79,
                            ""])
        expected = header + SAMPLE_GENERATED_ROLE
        self.assertEqual(expected, r)
        get_roles_mock.assert_called_with('/roles')
        check_mock.assert_called_with(['sample', 'bar', 'baz'],
                                      ['sample:sampleA'])

    @mock.patch('tripleo_common.utils.roles.check_role_exists')
    @mock.patch('tripleo_common.utils.roles.get_roles_list_from_directory')
    def test_generate_roles_with_two_same_roles(self, get_roles_mock,
                                                check_mock):
        get_roles_mock.return_value = ['sample', 'bar', 'baz']
        m = mock.mock_open(read_data=SAMPLE_ROLE)
        with mock.patch('tripleo_common.utils.roles.open', m) as open_mock:
            r = rolesutils.generate_roles_data_from_directory(
                '/roles', ['sample', 'sample:sampleA'])
            open_mock.assert_any_call('/roles/sample.yaml', 'r')

        header = '\n'.join(["#" * 79,
                            "# File generated by TripleO",
                            "#" * 79,
                            ""])
        expected = header + SAMPLE_ROLE + SAMPLE_GENERATED_ROLE
        self.assertEqual(expected, r)
        get_roles_mock.assert_called_with('/roles')
        check_mock.assert_called_with(['sample', 'bar', 'baz'],
                                      ['sample', 'sample:sampleA'])

    @mock.patch('tripleo_common.utils.roles.check_role_exists')
    @mock.patch('tripleo_common.utils.roles.get_roles_list_from_directory')
    def test_generate_roles_with_wrong_colon_format(self, get_roles_mock,
                                                    check_mock):
        get_roles_mock.return_value = ['sample', 'bar', 'baz']
        m = mock.mock_open(read_data=SAMPLE_ROLE)
        with mock.patch('tripleo_common.utils.roles.open', m) as open_mock:
            self.assertRaises(ValueError,
                              rolesutils.generate_roles_data_from_directory,
                              '/roles',
                              ['sample', 'sample:A'])
            open_mock.assert_any_call('/roles/sample.yaml', 'r')

    @mock.patch('tripleo_common.utils.roles.check_role_exists')
    @mock.patch('tripleo_common.utils.roles.get_roles_list_from_directory')
    def test_generate_roles_with_invalid_role_name(self, get_roles_mock,
                                                   check_mock):
        get_roles_mock.return_value = ['sample', 'bar', 'baz']
        m = mock.mock_open(read_data=SAMPLE_ROLE)
        with mock.patch('tripleo_common.utils.roles.open', m) as open_mock:
            self.assertRaises(ValueError,
                              rolesutils.generate_roles_data_from_directory,
                              '/roles',
                              ['sample', 'sampleA:sample'])
            open_mock.assert_any_call('/roles/sample.yaml', 'r')

    @mock.patch('tripleo_common.utils.roles.check_role_exists')
    @mock.patch('tripleo_common.utils.roles.get_roles_list_from_directory')
    def test_generate_roles_with_invalid_colon_format(self, get_roles_mock,
                                                      check_mock):
        get_roles_mock.return_value = ['sample', 'bar', 'baz']
        m = mock.mock_open(read_data=SAMPLE_ROLE)
        with mock.patch('tripleo_common.utils.roles.open', m) as open_mock:
            self.assertRaises(ValueError,
                              rolesutils.generate_roles_data_from_directory,
                              '/roles',
                              ['sample', 'sample:sample'])
            open_mock.assert_any_call('/roles/sample.yaml', 'r')
