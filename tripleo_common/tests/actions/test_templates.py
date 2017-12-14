# Copyright 2016 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import jinja2
import mock
import yaml

from heatclient import exc as heat_exc
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import templates
from tripleo_common import constants
from tripleo_common.tests import base

JINJA_SNIPPET = r"""
# Jinja loop for Role in role_data.yaml
{% for role in roles %}
  # Resources generated for {{role.name}} Role
  {{role.name}}ServiceChain:
    type: OS::TripleO::Services
    properties:
      Services:
        get_param: {{role.name}}Services
      ServiceNetMap: {get_attr: [ServiceNetMap, service_net_map]}
      EndpointMap: {get_attr: [EndpointMap, endpoint_map]}
      DefaultPasswords: {get_attr: [DefaultPasswords, passwords]}
{% endfor %}"""

ROLE_DATA_YAML = r"""
-
  name: CustomRole
"""

NETWORK_DATA_YAML = r"""
-
  name: InternalApi
"""

EXPECTED_JINJA_RESULT = r"""
# Jinja loop for Role in role_data.yaml

  # Resources generated for CustomRole Role
  CustomRoleServiceChain:
    type: OS::TripleO::Services
    properties:
      Services:
        get_param: CustomRoleServices
      ServiceNetMap: {get_attr: [ServiceNetMap, service_net_map]}
      EndpointMap: {get_attr: [EndpointMap, endpoint_map]}
      DefaultPasswords: {get_attr: [DefaultPasswords, passwords]}
"""

JINJA_SNIPPET_CONFIG = r"""
outputs:
  OS::stack_id:
    description: The software config which runs puppet on the {{role}} role
    value: {get_resource: {{role}}PuppetConfigImpl}"""

J2_EXCLUDES = r"""
name:
  - puppet/controller-role.yaml
"""

J2_EXCLUDES_EMPTY_LIST = r"""
name:
"""

J2_EXCLUDES_EMPTY_FILE = r"""
"""

ROLE_DATA_DISABLE_CONSTRAINTS_YAML = r"""
- name: RoleWithDisableConstraints
  disable_constraints: True
"""

ROLE_DATA_ENABLE_NETWORKS = r"""
- name: RoleWithNetworks
  networks:
    - InternalApi
"""

JINJA_SNIPPET_DISABLE_CONSTRAINTS_OLD = r"""
  {{role}}Image:
    type: string
    default: overcloud-full
{% if disable_constraints is not defined %}
    constraints:
      - custom_constraint: glance.image
{% endif %}
"""

JINJA_SNIPPET_DISABLE_CONSTRAINTS = r"""
  {{role.name}}Image:
    type: string
    default: overcloud-full
{% if role.disable_constraints is not defined %}
    constraints:
      - custom_constraint: glance.image
{% endif %}
"""

EXPECTED_JINJA_RESULT_DISABLE_CONSTRAINTS = r"""
  RoleWithDisableConstraintsImage:
    type: string
    default: overcloud-full
"""

JINJA_SNIPPET_ROLE_NETWORKS = r"""
{%- for network in networks %}
    {%- if network.name in role.networks%}
  {{network.name}}Port:
    type: {{role.name}}::{{network.name}}::Port
    {%- endif %}
{% endfor %}
"""

EXPECTED_JINJA_RESULT_ROLE_NETWORKS = r"""
  InternalApiPort:
    type: RoleWithNetworks::InternalApi::Port
"""


class UploadTemplatesActionTest(base.TestCase):

    @mock.patch('tempfile.NamedTemporaryFile')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('tripleo_common.utils.tarball.'
                'tarball_extract_to_swift_container')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run(self, mock_create_tar, mock_extract_tar, mock_get_swift,
                 tempfile):
        mock_ctx = mock.MagicMock()
        tempfile.return_value.__enter__.return_value.name = "test"

        action = templates.UploadTemplatesAction(container='tar-container')
        action.run(mock_ctx)

        mock_create_tar.assert_called_once_with(
            constants.DEFAULT_TEMPLATES_PATH, 'test')
        mock_extract_tar.assert_called_once_with(
            mock_get_swift.return_value, 'test', 'tar-container')


class J2SwiftLoaderTest(base.TestCase):
    @staticmethod
    def _setup_swift():
        def return_multiple_files(*args):
            if args[1] == 'bar/foo.yaml':
                return ['', 'I am foo']
            else:
                raise swiftexceptions.ClientException('not found')
        swift = mock.MagicMock()
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        return swift

    def test_include_absolute_path(self):
        j2_loader = templates.J2SwiftLoader(self._setup_swift(), None)
        template = jinja2.Environment(loader=j2_loader).from_string(
            r'''
            Included this:
            {% include 'bar/foo.yaml' %}
            ''')
        self.assertEqual(
            template.render(),
            '''
            Included this:
            I am foo
            ''')

    def test_include_search_path(self):
        j2_loader = templates.J2SwiftLoader(self._setup_swift(), None, 'bar')
        template = jinja2.Environment(loader=j2_loader).from_string(
            r'''
            Included this:
            {% include 'foo.yaml' %}
            ''')
        self.assertEqual(
            template.render(),
            '''
            Included this:
            I am foo
            ''')

    def test_include_not_found(self):
        j2_loader = templates.J2SwiftLoader(self._setup_swift(), None)
        template = jinja2.Environment(loader=j2_loader).from_string(
            r'''
            Included this:
            {% include 'bar.yaml' %}
            ''')
        self.assertRaises(
            jinja2.exceptions.TemplateNotFound,
            template.render)

    def test_include_invalid_path(self):
        j2_loader = templates.J2SwiftLoader(self._setup_swift(), 'bar')
        template = jinja2.Environment(loader=j2_loader).from_string(
            r'''
            Included this:
            {% include '../foo.yaml' %}
            ''')
        self.assertRaises(
            jinja2.exceptions.TemplateNotFound,
            template.render)


class ProcessTemplatesActionTest(base.TestCase):

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, mock_get_object_client,
                 mock_get_template_contents,
                 mock_process_multiple_environments_and_files):

        mock_ctx = mock.MagicMock()
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        # Test
        action = templates.ProcessTemplatesAction()
        result = action.run(mock_ctx)

        # Verify the values we get out
        self.assertEqual(result, {
            'environment': {},
            'files': {},
            'stack_name': constants.DEFAULT_CONTAINER_NAME,
            'template': {
                'heat_template_version': '2016-04-30'
            }
        })

    def _custom_roles_mock_objclient(self, snippet_name, snippet_content,
                                     role_data=None):

        def return_multiple_files(*args):
            if args[1] == constants.OVERCLOUD_J2_NAME:
                return ['', JINJA_SNIPPET]
            if args[1] == snippet_name:
                return ['', snippet_content]
            if args[1] == constants.OVERCLOUD_J2_EXCLUDES:
                return ['', J2_EXCLUDES]
            elif args[1] == constants.OVERCLOUD_J2_ROLES_NAME:
                return ['', role_data or ROLE_DATA_YAML]
            elif args[1] == constants.OVERCLOUD_J2_NETWORKS_NAME:
                return ['', NETWORK_DATA_YAML]

        def return_container_files(*args):
            return ('headers', [
                {'name': constants.OVERCLOUD_J2_NAME},
                {'name': snippet_name},
                {'name': constants.OVERCLOUD_J2_ROLES_NAME},
                {'name': constants.OVERCLOUD_J2_NETWORKS_NAME}])

        # setup swift
        swift = mock.MagicMock()
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)
        return swift

    @mock.patch('tripleo_common.actions.templates.ProcessTemplatesAction'
                '._heat_resource_exists')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_process_custom_roles(self, get_obj_client_mock,
                                  resource_exists_mock):
        resource_exists_mock.return_value = False
        swift = self._custom_roles_mock_objclient(
            'foo.j2.yaml', JINJA_SNIPPET)
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        mock_ctx = mock.MagicMock()
        action._process_custom_roles(mock_ctx)

        get_object_mock_calls = [
            mock.call('overcloud', constants.OVERCLOUD_J2_NAME),
            mock.call('overcloud', constants.OVERCLOUD_J2_ROLES_NAME),
            mock.call('overcloud', 'foo.j2.yaml'),
        ]
        swift.get_object.assert_has_calls(
            get_object_mock_calls, any_order=True)

        put_object_mock_calls = [
            mock.call(constants.DEFAULT_CONTAINER_NAME,
                      constants.OVERCLOUD_YAML_NAME,
                      EXPECTED_JINJA_RESULT),
            mock.call(constants.DEFAULT_CONTAINER_NAME,
                      'foo.yaml',
                      EXPECTED_JINJA_RESULT),
        ]
        swift.put_object.assert_has_calls(
            put_object_mock_calls, any_order=True)

    @mock.patch('tripleo_common.actions.templates.ProcessTemplatesAction'
                '._heat_resource_exists')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def _process_custom_roles_disable_constraints(
            self, snippet, get_obj_client_mock, resource_exists_mock):
        resource_exists_mock.return_value = False
        swift = self._custom_roles_mock_objclient(
            'disable-constraints.role.j2.yaml', snippet,
            ROLE_DATA_DISABLE_CONSTRAINTS_YAML)
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        mock_ctx = mock.MagicMock()
        action._process_custom_roles(mock_ctx)

        expected = EXPECTED_JINJA_RESULT.replace(
            'CustomRole', 'RoleWithDisableConstraints')
        put_object_mock_call = mock.call(
            constants.DEFAULT_CONTAINER_NAME,
            'overcloud.yaml',
            expected)
        self.assertEqual(swift.put_object.call_args_list[0],
                         put_object_mock_call)

        put_object_mock_call = mock.call(
            constants.DEFAULT_CONTAINER_NAME,
            "rolewithdisableconstraints-disable-constraints.yaml",
            EXPECTED_JINJA_RESULT_DISABLE_CONSTRAINTS)
        self.assertEqual(put_object_mock_call,
                         swift.put_object.call_args_list[1])

    def test_process_custom_roles_disable_constraints_old(self):
        self._process_custom_roles_disable_constraints(
            JINJA_SNIPPET_DISABLE_CONSTRAINTS_OLD)

    def test_process_custom_roles_disable_constraints(self):
        self._process_custom_roles_disable_constraints(
            JINJA_SNIPPET_DISABLE_CONSTRAINTS)

    @mock.patch('tripleo_common.actions.templates.ProcessTemplatesAction'
                '._heat_resource_exists')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_custom_roles_networks(self, get_obj_client_mock,
                                   resource_exists_mock):
        resource_exists_mock.return_value = False
        swift = self._custom_roles_mock_objclient(
            'role-networks.role.j2.yaml', JINJA_SNIPPET_ROLE_NETWORKS,
            ROLE_DATA_ENABLE_NETWORKS)
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        mock_ctx = mock.MagicMock()
        action._process_custom_roles(mock_ctx)

        expected = EXPECTED_JINJA_RESULT.replace(
            'CustomRole', 'RoleWithNetworks')
        put_object_mock_call = mock.call(
            constants.DEFAULT_CONTAINER_NAME,
            'overcloud.yaml',
            expected)
        self.assertEqual(swift.put_object.call_args_list[0],
                         put_object_mock_call)

        put_object_mock_call = mock.call(
            constants.DEFAULT_CONTAINER_NAME,
            "rolewithnetworks-role-networks.yaml",
            EXPECTED_JINJA_RESULT_ROLE_NETWORKS)
        self.assertEqual(put_object_mock_call,
                         swift.put_object.call_args_list[1])

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_j2_render_and_put(self, get_obj_client_mock):

        # setup swift
        swift = mock.MagicMock()
        swift.get_object = mock.MagicMock()
        swift.get_container = mock.MagicMock()
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        action._j2_render_and_put(JINJA_SNIPPET_CONFIG,
                                  {'role': 'CustomRole'},
                                  'customrole-config.yaml')

        action_result = swift.put_object._mock_mock_calls[0]

        self.assertTrue("CustomRole" in str(action_result))

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_j2_render_and_put_include(self, get_obj_client_mock):

        def return_multiple_files(*args):
            if args[1] == 'foo.yaml':
                return ['', JINJA_SNIPPET_CONFIG]

        def return_container_files(*args):
            return ('headers', [{'name': 'foo.yaml'}])

        # setup swift
        swift = mock.MagicMock()
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        action._j2_render_and_put(r"{% include 'foo.yaml' %}",
                                  {'role': 'CustomRole'},
                                  'customrole-config.yaml')

        action_result = swift.put_object._mock_mock_calls[0]

        self.assertTrue("CustomRole" in str(action_result))

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_j2_render_and_put_include_relative(
            self,
            get_obj_client_mock):

        def return_multiple_files(*args):
            if args[1] == 'bar/foo.yaml':
                return ['', JINJA_SNIPPET_CONFIG]

        def return_container_files(*args):
            return ('headers', [{'name': 'bar/foo.yaml'}])

        # setup swift
        swift = mock.MagicMock()
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        action._j2_render_and_put(r"{% include 'foo.yaml' %}",
                                  {'role': 'CustomRole'},
                                  'bar/customrole-config.yaml')

        action_result = swift.put_object._mock_mock_calls[0]

        self.assertTrue("CustomRole" in str(action_result))

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_get_j2_excludes_file(self, get_obj_client_mock):

        mock_ctx = mock.MagicMock()
        swift = mock.MagicMock()
        get_obj_client_mock.return_value = swift

        def return_multiple_files(*args):
            if args[1] == constants.OVERCLOUD_J2_EXCLUDES:
                return ['', J2_EXCLUDES]
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        # Test - J2 exclude file with valid templates
        action = templates.ProcessTemplatesAction()
        self.assertTrue({'name': ['puppet/controller-role.yaml']} ==
                        action._get_j2_excludes_file(mock_ctx))

        def return_multiple_files(*args):
            if args[1] == constants.OVERCLOUD_J2_EXCLUDES:
                return ['', J2_EXCLUDES_EMPTY_LIST]
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        # Test - J2 exclude file with no template to exlude
        action = templates.ProcessTemplatesAction()
        self.assertTrue({'name': []} == action._get_j2_excludes_file(mock_ctx))

        def return_multiple_files(*args):
            if args[1] == constants.OVERCLOUD_J2_EXCLUDES:
                return ['', J2_EXCLUDES_EMPTY_FILE]
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        # Test - J2 exclude file empty
        action = templates.ProcessTemplatesAction()
        self.assertTrue({'name': []} == action._get_j2_excludes_file(mock_ctx))

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_heat_resource_exists(self, client_mock):
        mock_ctx = mock.MagicMock()
        heat_client = mock.MagicMock()
        heat_client.stacks.get.return_value = mock.MagicMock(
            stack_name='overcloud')
        heat_client.resources.get.return_value = mock.MagicMock(
            links=[{'rel': 'stack',
                    'href': 'http://192.0.2.1:8004/v1/'
                            'a959ac7d6a4a475daf2428df315c41ef/'
                            'stacks/overcloud/123'}],
            logical_resource_id='logical_id',
            physical_resource_id='resource_id',
            resource_type='OS::Heat::ResourceGroup',
            resource_name='InternalApiNetwork'
        )
        client_mock.return_value = heat_client
        action = templates.ProcessTemplatesAction()
        self.assertTrue(
            action._heat_resource_exists(
                'Networks', 'InternalNetwork', mock_ctx))

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    def test_no_heat_resource_exists(self, client_mock):
        mock_ctx = mock.MagicMock()
        heat_client = mock.MagicMock()
        heat_client.stacks.get.return_value = mock.MagicMock(
            stack_name='overcloud')

        def return_not_found(*args):
            raise heat_exc.HTTPNotFound()

        heat_client.resources.get.side_effect = return_not_found
        client_mock.return_value = heat_client
        action = templates.ProcessTemplatesAction()
        self.assertFalse(
            action._heat_resource_exists(
                'Networks', 'InternalNetwork', mock_ctx))

    @mock.patch('tripleo_common.actions.templates.ProcessTemplatesAction'
                '._heat_resource_exists')
    @mock.patch('tripleo_common.actions.templates.ProcessTemplatesAction'
                '._j2_render_and_put')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_legacy_api_network_exists(self, get_obj_client_mock, j2_mock,
                                       resource_exists_mock):
        resource_exists_mock.return_value = True
        swift = self._custom_roles_mock_objclient(
            'role-networks.role.j2.yaml', JINJA_SNIPPET_ROLE_NETWORKS,
            ROLE_DATA_ENABLE_NETWORKS)
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        mock_ctx = mock.MagicMock()
        action._process_custom_roles(mock_ctx)
        expected_j2_template = get_obj_client_mock.get_object(
            action.container, 'foo.j2.yaml')[1]
        expected_j2_data = {'roles': [{'name': 'CustomRole'}],
                            'networks': [{'name': 'InternalApi',
                                          'compat_name': 'Internal'}]
                            }
        assert j2_mock.called_with(expected_j2_template, expected_j2_data,
                                   'foo.yaml', mock_ctx)

    @mock.patch('tripleo_common.actions.templates.ProcessTemplatesAction'
                '._heat_resource_exists')
    @mock.patch('tripleo_common.actions.templates.ProcessTemplatesAction'
                '._j2_render_and_put')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_no_legacy_api_network_exists(self, get_obj_client_mock, j2_mock,
                                          resource_exists_mock):
        resource_exists_mock.return_value = False
        swift = self._custom_roles_mock_objclient(
            'role-networks.role.j2.yaml', JINJA_SNIPPET_ROLE_NETWORKS,
            ROLE_DATA_ENABLE_NETWORKS)
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        mock_ctx = mock.MagicMock()
        action._process_custom_roles(mock_ctx)
        expected_j2_template = get_obj_client_mock.get_object(
            action.container, 'foo.j2.yaml')[1]
        expected_j2_data = {'roles': [{'name': 'CustomRole'}],
                            'networks': [{'name': 'InternalApi'}]
                            }
        assert j2_mock.called_with(expected_j2_template, expected_j2_data,
                                   'foo.yaml', mock_ctx)
