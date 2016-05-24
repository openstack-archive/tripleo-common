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

from tripleo_common.actions import plan
from tripleo_common import exception
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


class CreateContainerActionTest(base.TestCase):

    def setUp(self):
        super(CreateContainerActionTest, self).setUp()
        self.container_name = 'test-container'
        self.expected_list = ['', [{'name': 'test1'}, {'name': 'test2'}]]

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    def test_run(self, get_obj_client_mock):

        # Setup
        swift = mock.MagicMock()
        swift.get_account.return_value = self.expected_list
        get_obj_client_mock.return_value = swift

        # Test
        action = plan.CreateContainerAction(self.container_name)
        action.run()

        # Verify
        swift.put_container.assert_called_once_with(
            self.container_name,
            headers=plan.default_container_headers
        )

    @mock.patch('tripleo_common.actions.base.TripleOAction._get_object_client')
    def test_run_container_exists(self, get_obj_client_mock):

        # Setup
        swift = mock.MagicMock()
        swift.get_account.return_value = [
            '', [{'name': 'test-container'}, {'name': 'test2'}]]
        get_obj_client_mock.return_value = swift

        # Test
        action = plan.CreateContainerAction(self.container_name)

        self.assertRaises(exception.ContainerAlreadyExistsError, action.run)


class CreatePlanActionTest(base.TestCase):

    def setUp(self):
        super(CreatePlanActionTest, self).setUp()
        self.container_name = 'test-container'
        self.capabilities_name = 'capabilities-map.yaml'

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

        # Test
        action = plan.CreatePlanAction(self.container_name)
        action.run()

        # verify
        swift.get_object.assert_called_once_with(
            self.container_name,
            self.capabilities_name
        )

        mistral.environments.create.assert_called_once_with(
            name='test-container',
            variables=('{"environments":'
                       ' [{"path": "/path/to/environment.yaml"}], '
                       '"template": "/path/to/overcloud.yaml"}')
        )
