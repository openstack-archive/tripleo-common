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
import mock

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

ROLE_DATA_ENABLE_NETWORKS = r"""
- name: RoleWithNetworks
  networks:
    - InternalApi
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
