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

from mistral.workflow import utils as mistral_workflow_utils

from tripleo_common.actions import heat_capabilities
from tripleo_common.tests import base


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


class GetCapabilitiesActionTest(base.TestCase):

    def setUp(self):
        super(GetCapabilitiesActionTest, self).setUp()
        self.container_name = 'test-container'

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    def test_run_yaml_error(self, get_obj_client_mock):
        # setup swift
        swift = mock.MagicMock()
        swift.get_object.return_value = mock.Mock(side_effect=ValueError)
        get_obj_client_mock.return_value = swift

        action = heat_capabilities.GetCapabilitiesAction(self.container_name)
        expected = mistral_workflow_utils.Result(
            data=None,
            error="Error parsing capabilities-map.yaml.")
        self.assertEqual(expected, action.run())

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction._get_workflow_client')
    def test_run_mistral_error(self, get_workflow_client_mock,
                               get_obj_client_mock):

        # setup swift
        swift = mock.MagicMock()
        swift.get_object.return_value = ({}, MAPPING_YAML_CONTENTS)
        get_obj_client_mock.return_value = swift

        # setup mistral
        mistral = mock.MagicMock()
        mistral.environments.get = mock.Mock(
            side_effect=Exception)
        get_workflow_client_mock.return_value = mistral

        action = heat_capabilities.GetCapabilitiesAction(self.container_name)
        expected = mistral_workflow_utils.Result(
            data=None,
            error="Error retrieving mistral environment. ")
        self.assertEqual(expected, action.run())

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction._get_workflow_client')
    def test_run(self, get_workflow_client_mock, get_obj_client_mock):

        # setup swift
        swift = mock.MagicMock()
        swift.get_object.return_value = ({}, MAPPING_YAML_CONTENTS)
        get_obj_client_mock.return_value = swift

        # setup mistral
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral

        action = heat_capabilities.GetCapabilitiesAction(self.container_name)
        self.assertEqual({
            '/path/to/ceph-storage-env.yaml': {'enabled': False},
            '/path/to/network-isolation.json': {'enabled': False},
            '/path/to/poc-custom-env.yaml': {'enabled': False}},
            action.run())


class UpdateCapabilitiesActionTest(base.TestCase):

    def setUp(self,):
        super(UpdateCapabilitiesActionTest, self).setUp()
        self.container_name = 'test-container'

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction._get_workflow_client')
    def test_run(self, get_workflow_client_mock):

        # setup mistral
        mistral = mock.MagicMock()
        mocked_env = mock.MagicMock()
        mocked_env.variables = {
            'environments': [
                {'path': '/path/to/overcloud-default-env.yaml'}
            ]
        }
        mistral.environments.get.return_value = mocked_env
        get_workflow_client_mock.return_value = mistral

        environments = {'/path/to/ceph-storage-env.yaml': {'enabled': False},
                        '/path/to/network-isolation.json': {'enabled': False},
                        '/path/to/poc-custom-env.yaml': {'enabled': True}}

        action = heat_capabilities.UpdateCapabilitiesAction(
            environments, self.container_name)
        self.assertEqual({
            'environments': [
                {'path': '/path/to/overcloud-default-env.yaml'},
                {'path': '/path/to/poc-custom-env.yaml'}
            ]},
            action.run().variables)

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction._get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction._get_workflow_client')
    def test_run_mistral_error(self, get_workflow_client_mock,
                               get_obj_client_mock):

        # setup swift
        swift = mock.MagicMock()
        swift.get_object.return_value = ({}, MAPPING_YAML_CONTENTS)
        get_obj_client_mock.return_value = swift

        # setup mistral
        mistral = mock.MagicMock()
        mistral.environments.get = mock.Mock(
            side_effect=Exception)
        get_workflow_client_mock.return_value = mistral

        action = heat_capabilities.UpdateCapabilitiesAction(
            {}, self.container_name)
        expected = mistral_workflow_utils.Result(
            data=None,
            error="Error retrieving mistral environment. ")
        self.assertEqual(expected, action.run())
