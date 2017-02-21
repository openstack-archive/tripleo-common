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
  name: anetwork
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

JINJA_SNIPPET_DISABLE_CONSTRAINTS = r"""
  {{role}}Image:
    type: string
    default: overcloud-full
{% if disable_constraints is not defined %}
    constraints:
      - custom_constraint: glance.image
{% endif %}
"""

EXPECTED_JINJA_RESULT_DISABLE_CONSTRAINTS = r"""
  RoleWithDisableConstraintsImage:
    type: string
    default: overcloud-full
"""


class UploadTemplatesActionTest(base.TestCase):

    @mock.patch('tempfile.NamedTemporaryFile')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('tripleo_common.utils.tarball.'
                'tarball_extract_to_swift_container')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run(self, mock_create_tar, mock_extract_tar, mock_get_swift,
                 tempfile):

        tempfile.return_value.__enter__.return_value.name = "test"

        action = templates.UploadTemplatesAction(container='tar-container')
        action.run()

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
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('mistral.context.ctx')
    def test_run(self, mock_ctx, mock_get_object_client,
                 mock_get_workflow_client, mock_get_template_contents,
                 mock_process_multiple_environments_and_files):

        mock_ctx.return_value = mock.MagicMock()
        swift = mock.MagicMock(url="http://test.com")
        swift.get_object.side_effect = swiftexceptions.ClientException(
            'atest2')
        mock_get_object_client.return_value = swift

        mock_mistral = mock.MagicMock()
        mock_env = mock.MagicMock()
        mock_env.variables = {
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }
        mock_mistral.environments.get.return_value = mock_env
        mock_get_workflow_client.return_value = mock_mistral

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        # Test
        action = templates.ProcessTemplatesAction()
        result = action.run()

        # Verify the values we get out
        self.assertEqual(result, {
            'environment': {},
            'files': {},
            'stack_name': constants.DEFAULT_CONTAINER_NAME,
            'template': {
                'heat_template_version': '2016-04-30'
            }
        })

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('mistral.context.ctx')
    def test_process_custom_roles(self, ctx_mock, get_obj_client_mock):

        def return_multiple_files(*args):
            if args[1] == constants.OVERCLOUD_J2_NAME:
                return ['', JINJA_SNIPPET]
            if args[1] == 'foo.j2.yaml':
                return ['', JINJA_SNIPPET]
            if args[1] == constants.OVERCLOUD_J2_EXCLUDES:
                return ['', J2_EXCLUDES]
            elif args[1] == constants.OVERCLOUD_J2_ROLES_NAME:
                return ['', ROLE_DATA_YAML]
            elif args[1] == constants.OVERCLOUD_J2_NETWORKS_NAME:
                return ['', NETWORK_DATA_YAML]

        def return_container_files(*args):
            return ('headers', [
                {'name': constants.OVERCLOUD_J2_NAME},
                {'name': 'foo.j2.yaml'},
                {'name': constants.OVERCLOUD_J2_ROLES_NAME},
                {'name': constants.OVERCLOUD_J2_NETWORKS_NAME}])

        # setup swift
        swift = mock.MagicMock()
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        action._process_custom_roles()

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

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('mistral.context.ctx')
    def test_process_custom_roles_disable_constraints(
            self, ctx_mock, get_obj_client_mock):

        def return_multiple_files(*args):
            if args[1] == constants.OVERCLOUD_J2_NAME:
                return ['', JINJA_SNIPPET_DISABLE_CONSTRAINTS]
            if args[1] == 'disable-constraints.role.j2.yaml':
                return ['', JINJA_SNIPPET_DISABLE_CONSTRAINTS]
            if args[1] == constants.OVERCLOUD_J2_EXCLUDES:
                return ['', J2_EXCLUDES]
            elif args[1] == constants.OVERCLOUD_J2_ROLES_NAME:
                return ['', ROLE_DATA_DISABLE_CONSTRAINTS_YAML]
            elif args[1] == constants.OVERCLOUD_J2_NETWORKS_NAME:
                return ['', NETWORK_DATA_YAML]

        def return_container_files(*args):
            return ('headers', [
                {'name': constants.OVERCLOUD_J2_NAME},
                {'name': 'disable-constraints.role.j2.yaml'},
                {'name': constants.OVERCLOUD_J2_ROLES_NAME},
                {'name': constants.OVERCLOUD_J2_NETWORKS_NAME}])

        # setup swift
        swift = mock.MagicMock()
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)
        get_obj_client_mock.return_value = swift

        # Test
        action = templates.ProcessTemplatesAction()
        action._process_custom_roles()

        put_object_mock_call = mock.call(
            constants.DEFAULT_CONTAINER_NAME,
            "rolewithdisableconstraints-disable-constraints.yaml",
            EXPECTED_JINJA_RESULT_DISABLE_CONSTRAINTS)
        self.assertEqual(swift.put_object.call_args_list[1],
                         put_object_mock_call)

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('mistral.context.ctx')
    def test_j2_render_and_put(self, ctx_mock, get_obj_client_mock):

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
    @mock.patch('mistral.context.ctx')
    def test_j2_render_and_put_include(self, ctx_mock, get_obj_client_mock):

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
    @mock.patch('mistral.context.ctx')
    def test_j2_render_and_put_include_relative(
            self,
            ctx_mock,
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
    @mock.patch('mistral.context.ctx')
    def test_get_j2_excludes_file(self, ctx_mock, get_obj_client_mock):

        swift = mock.MagicMock()
        get_obj_client_mock.return_value = swift

        def return_multiple_files(*args):
            if args[1] == constants.OVERCLOUD_J2_EXCLUDES:
                return ['', J2_EXCLUDES]
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        # Test - J2 exclude file with valid templates
        action = templates.ProcessTemplatesAction()
        self.assertTrue({'name': ['puppet/controller-role.yaml']} ==
                        action._get_j2_excludes_file())

        def return_multiple_files(*args):
            if args[1] == constants.OVERCLOUD_J2_EXCLUDES:
                return ['', J2_EXCLUDES_EMPTY_LIST]
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        # Test - J2 exclude file with no template to exlude
        action = templates.ProcessTemplatesAction()
        self.assertTrue({'name': []} == action._get_j2_excludes_file())

        def return_multiple_files(*args):
            if args[1] == constants.OVERCLOUD_J2_EXCLUDES:
                return ['', J2_EXCLUDES_EMPTY_FILE]
        swift.get_object = mock.MagicMock(side_effect=return_multiple_files)
        # Test - J2 exclude file empty
        action = templates.ProcessTemplatesAction()
        self.assertTrue({'name': []} == action._get_j2_excludes_file())
