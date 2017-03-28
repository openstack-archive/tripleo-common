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
import json
import mock

from heatclient import exc as heatexceptions
from mistral.workflow import utils as mistral_workflow_utils
from mistralclient.api import base as mistral_base
from oslo_concurrency import processutils
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import plan
from tripleo_common import constants
from tripleo_common import exception
from tripleo_common.tests import base

JSON_CONTENTS = json.dumps({
    "environments": [{
        "path": "overcloud-resource-registry-puppet.yaml"
    }, {
        "path": "environments/services/sahara.yaml"
    }],
    "parameter_defaults": {
        "BlockStorageCount": 42,
        "OvercloudControlFlavor": "yummy"
    },
    "passwords": {
        "AdminPassword": "aaaa",
        "ZaqarPassword": "zzzz"
    },
    "template": "overcloud.yaml",
    "version": 1.0
}, sort_keys=True)


YAML_CONTENTS = """
version: 1.0

template: overcloud.yaml
environments:
-  path: overcloud-resource-registry-puppet.yaml
-  path: environments/services/sahara.yaml
parameter_defaults:
  BlockStorageCount: 42
  OvercloudControlFlavor: yummy
passwords:
  AdminPassword: aaaa
  ZaqarPassword: zzzz
"""

YAML_CONTENTS_INVALID = "{bad_yaml"

# `environments` is missing
YAML_CONTENTS_MISSING_KEY = """
template: overcloud.yaml
"""

RESOURCES_YAML_CONTENTS = """heat_template_version: 2016-04-08
resources:
  Controller:
    type: OS::Heat::ResourceGroup
  NotRoleContoller:
    type: OS::Dummy::DummyGroup
  Compute:
    type: OS::Heat::ResourceGroup
notresources:
  BlockStorageDummy:
    type: OS::Heat::ResourceGroup
"""


class CreateContainerActionTest(base.TestCase):

    def setUp(self):
        super(CreateContainerActionTest, self).setUp()
        # A container that name enforces all validation rules
        self.container_name = 'Test-container-7'
        self.expected_list = ['', [{'name': 'test1'}, {'name': 'test2'}]]

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
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

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_container_exists(self, get_obj_client_mock):

        # Setup
        swift = mock.MagicMock()
        swift.get_account.return_value = [
            '', [{'name': 'Test-container-7'}, {'name': 'test2'}]]
        get_obj_client_mock.return_value = swift

        # Test
        action = plan.CreateContainerAction(self.container_name)
        result = action.run()

        error_str = ('A container with the name %s already'
                     ' exists.') % self.container_name
        self.assertEqual(result, mistral_workflow_utils.Result(
            None, error_str))

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_invalid_name(self, get_obj_client_mock):
        # Setup
        swift = mock.MagicMock()
        get_obj_client_mock.return_value = swift

        # Test
        action = plan.CreateContainerAction("invalid_underscore")
        result = action.run()

        error_str = ("Unable to create plan. The plan name must only contain "
                     "letters, numbers or dashes")
        self.assertEqual(result, mistral_workflow_utils.Result(
            None, error_str))


class CreatePlanActionTest(base.TestCase):

    def setUp(self):
        super(CreatePlanActionTest, self).setUp()
        # A container that name enforces all validation rules
        self.container_name = 'Test-container-3'
        self.plan_environment_name = constants.PLAN_ENVIRONMENT

        # setup swift
        self.swift = mock.MagicMock()
        self.swift.get_object.return_value = ({}, YAML_CONTENTS)
        swift_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_object_client',
            return_value=self.swift)
        swift_patcher.start()
        self.addCleanup(swift_patcher.stop)

        # setup mistral
        self.mistral = mock.MagicMock()
        self.mistral.environments.get.side_effect = mistral_base.APIException
        mistral_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_workflow_client',
            return_value=self.mistral)
        mistral_patcher.start()
        self.addCleanup(mistral_patcher.stop)

    def test_run_success(self):
        action = plan.CreatePlanAction(self.container_name)
        action.run()

        self.swift.get_object.assert_called_once_with(
            self.container_name,
            self.plan_environment_name
        )

        self.swift.delete_object.assert_called_once()

        self.mistral.environments.create.assert_called_once_with(
            name='Test-container-3',
            variables=JSON_CONTENTS
        )

    def test_run_invalid_plan_name(self):
        action = plan.CreatePlanAction("invalid_underscore")
        result = action.run()

        error_str = ("Unable to create plan. The plan name must only contain "
                     "letters, numbers or dashes")
        # don't bother checking the exact error (python versions different)
        self.assertEqual(result.error.split(':')[0], error_str)

    def test_run_mistral_env_already_exists(self):
        self.mistral.environments.get.side_effect = None
        self.mistral.environments.get.return_value = 'test-env'

        action = plan.CreatePlanAction(self.container_name)
        result = action.run()

        error_str = ("Unable to create plan. The Mistral environment already "
                     "exists")
        self.assertEqual(result.error, error_str)
        self.mistral.environments.create.assert_not_called()

    def test_run_missing_file(self):
        self.swift.get_object.side_effect = swiftexceptions.ClientException(
            self.plan_environment_name)

        action = plan.CreatePlanAction(self.container_name)
        result = action.run()

        error_str = ('File missing from container: %s' %
                     self.plan_environment_name)
        self.assertEqual(result.error, error_str)

    def test_run_invalid_yaml(self):
        self.swift.get_object.return_value = ({}, YAML_CONTENTS_INVALID)

        action = plan.CreatePlanAction(self.container_name)
        result = action.run()

        error_str = 'Error parsing the yaml file'
        self.assertEqual(result.error.split(':')[0], error_str)

    def test_run_missing_key(self):
        self.swift.get_object.return_value = ({}, YAML_CONTENTS_MISSING_KEY)

        action = plan.CreatePlanAction(self.container_name)
        result = action.run()

        error_str = ("%s missing key: environments" %
                     self.plan_environment_name)
        self.assertEqual(result.error, error_str)


class UpdatePlanActionTest(base.TestCase):

    def setUp(self):
        super(UpdatePlanActionTest, self).setUp()
        self.container_name = 'Test-container-3'
        self.plan_environment_name = constants.PLAN_ENVIRONMENT

        # setup swift
        self.swift = mock.MagicMock()
        self.swift.get_object.return_value = ({}, YAML_CONTENTS)
        swift_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_object_client',
            return_value=self.swift)
        swift_patcher.start()
        self.addCleanup(swift_patcher.stop)

        # setup mistral
        self.mistral = mock.MagicMock()
        mistral_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_workflow_client',
            return_value=self.mistral)
        mistral_patcher.start()
        self.addCleanup(mistral_patcher.stop)

    def test_run_success(self):
        action = plan.UpdatePlanAction(self.container_name)
        action.run()

        self.swift.get_object.assert_called_once_with(
            self.container_name,
            self.plan_environment_name
        )

        self.swift.delete_object.assert_called_once()

        self.mistral.environments.update.assert_called_once_with(
            name='Test-container-3',
            variables=JSON_CONTENTS
        )

    def test_run_mistral_env_missing(self):
        self.mistral.environments.update.side_effect = (
            mistral_base.APIException)

        action = plan.UpdatePlanAction(self.container_name)
        result = action.run()

        error_str = ("Error updating mistral environment: %s" %
                     self.container_name)
        self.assertEqual(result.error, error_str)
        self.swift.delete_object.assert_not_called()

    def test_run_missing_file(self):
        self.swift.get_object.side_effect = swiftexceptions.ClientException(
            self.plan_environment_name)

        action = plan.UpdatePlanAction(self.container_name)
        result = action.run()

        error_str = ('File missing from container: %s' %
                     self.plan_environment_name)
        self.assertEqual(result.error, error_str)

    def test_run_invalid_yaml(self):
        self.swift.get_object.return_value = ({}, YAML_CONTENTS_INVALID)

        action = plan.UpdatePlanAction(self.container_name)
        result = action.run()

        error_str = 'Error parsing the yaml file'
        self.assertEqual(result.error.split(':')[0], error_str)

    def test_run_missing_key(self):
        self.swift.get_object.return_value = ({}, YAML_CONTENTS_MISSING_KEY)

        action = plan.UpdatePlanAction(self.container_name)
        result = action.run()

        error_str = ("%s missing key: environments" %
                     self.plan_environment_name)
        self.assertEqual(result.error, error_str)


class ListPlansActionTest(base.TestCase):

    def setUp(self):
        super(ListPlansActionTest, self).setUp()
        self.container = 'overcloud'

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_run(self, get_workflow_client_mock, get_obj_client_mock):

        # setup swift
        swift = mock.MagicMock()
        swift.get_account.return_value = ({}, [
            {
                'count': 1,
                'bytes': 55,
                'name': 'overcloud'
            },
        ])
        swift.get_container.return_value = ({
            'x-container-meta-usage-tripleo': 'plan',
        }, [])
        get_obj_client_mock.return_value = swift

        # setup mistral
        mistral = mock.MagicMock()
        env_item = mock.Mock()
        env_item.name = self.container
        mistral.environments.list.return_value = [env_item]
        get_workflow_client_mock.return_value = mistral

        # Test
        action = plan.ListPlansAction()
        action.run()

        # verify
        self.assertEqual([self.container], action.run())
        swift.get_account.assert_called()
        swift.get_container.assert_called_with(self.container)


class DeletePlanActionTest(base.TestCase):

    def setUp(self):
        super(DeletePlanActionTest, self).setUp()
        self.container_name = 'overcloud'
        self.stack = mock.MagicMock(
            id='123',
            status='CREATE_COMPLETE',
            stack_name=self.container_name
        )

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_orchestration_client')
    def test_run_stack_exists(self, get_orchestration_client):

        # setup heat
        heat = mock.MagicMock()
        heat.stacks.get.return_value = self.stack
        get_orchestration_client.return_value = heat

        # test that stack exists
        action = plan.DeletePlanAction(self.container_name)
        self.assertRaises(exception.StackInUseError, action.run)
        heat.stacks.get.assert_called_with(self.container_name)

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_orchestration_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_run(self, get_workflow_client_mock, get_orchestration_client,
                 get_obj_client_mock):

        # setup swift
        swift = mock.MagicMock()
        swift.get_account.return_value = ({}, [
            {'name': self.container_name},
            {'name': 'test'},
        ])
        swift.get_container.return_value = (
            {'x-container-meta-usage-tripleo': 'plan'}, [
                {'name': 'some-name.yaml'},
                {'name': 'some-other-name.yaml'},
                {'name': 'yet-some-other-name.yaml'},
                {'name': 'finally-another-name.yaml'}
            ]
        )

        get_obj_client_mock.return_value = swift

        # setup mistral
        mistral = mock.MagicMock()
        mistral_environment = mock.Mock()
        mistral_environment.name = self.container_name
        mistral.environments.list.return_value = [
            mistral_environment,
        ]
        get_workflow_client_mock.return_value = mistral

        # setup heat
        heat = mock.MagicMock()
        heat.stacks.get = mock.Mock(
            side_effect=heatexceptions.HTTPNotFound)
        get_orchestration_client.return_value = heat

        action = plan.DeletePlanAction(self.container_name)
        action.run()

        mock_calls = [
            mock.call('overcloud', 'some-name.yaml'),
            mock.call('overcloud', 'some-other-name.yaml'),
            mock.call('overcloud', 'yet-some-other-name.yaml'),
            mock.call('overcloud', 'finally-another-name.yaml')
        ]
        swift.delete_object.assert_has_calls(
            mock_calls, any_order=True)

        swift.delete_container.assert_called_with(self.container_name)

        mistral.environments.delete.assert_called_with(self.container_name)


class RoleListActionTest(base.TestCase):

    def setUp(self):
        super(RoleListActionTest, self).setUp()
        self.container = 'overcloud'

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_run(self, workflow_client_mock, get_obj_client_mock):

        # setup mistral
        mistral = mock.MagicMock()
        env_item = mock.Mock()
        mistral.environments.get.return_value = env_item
        workflow_client_mock.return_value = mistral

        env_item.variables = {
            'template': 'overcloud.yaml',
            'environments': [
                {'path': 'overcloud-resource-registry-puppet.yaml'}
            ]
        }
        env_item.name = self.container
        env_item.description = None
        env_item.created_at = '2016-06-30 15:51:09'
        env_item.updated_at = None
        env_item.scope = 'private'
        env_item.id = '4b5e97d0-2f7a-4cdd-ab7c-71331cce477d'

        # setup swift
        swift = mock.MagicMock()
        swift.get_object.return_value = ({}, RESOURCES_YAML_CONTENTS)
        get_obj_client_mock.return_value = swift

        template_name = workflow_client_mock().environments.get(
            self.container).variables['template']

        # Test
        action = plan.ListRolesAction()
        result = action.run()

        # verify
        expected = ['Compute', 'Controller']
        result.sort()
        self.assertEqual(expected, result)
        self.assertEqual('overcloud.yaml', template_name)
        swift.get_object.assert_called_with(self.container, template_name)


class ExportPlanActionTest(base.TestCase):

    def setUp(self):
        super(ExportPlanActionTest, self).setUp()
        self.plan = 'overcloud'
        self.delete_after = 3600
        self.exports_container = 'plan-exports'

        # setup swift
        self.template_files = (
            'some-name.yaml',
            'some-other-name.yaml',
            'yet-some-other-name.yaml',
            'finally-another-name.yaml'
        )
        self.swift = mock.MagicMock()
        self.swift.get_container.return_value = (
            {'x-container-meta-usage-tripleo': 'plan'}, [
                {'name': tf} for tf in self.template_files
            ]
        )
        self.swift.get_object.return_value = ({}, RESOURCES_YAML_CONTENTS)
        swift_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_object_client',
            return_value=self.swift)
        swift_patcher.start()
        self.addCleanup(swift_patcher.stop)

        # setup mistral
        self.mistral = mock.MagicMock()
        env_item = mock.Mock()
        env_item.variables = {
            'template': 'overcloud.yaml',
            'environments': [
                {'path': 'overcloud-resource-registry-puppet.yaml'}
            ]
        }
        self.mistral.environments.get.return_value = env_item
        mistral_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_workflow_client',
            return_value=self.mistral)
        mistral_patcher.start()
        self.addCleanup(mistral_patcher.stop)

    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    @mock.patch('tempfile.mkdtemp')
    def test_run_success(self, mock_mkdtemp, mock_create_tarball):
        get_object_mock_calls = [
            mock.call(self.plan, tf) for tf in self.template_files
        ]
        get_container_mock_calls = [
            mock.call(self.plan),
            mock.call('plan-exports')
        ]
        mock_mkdtemp.return_value = '/tmp/test123'

        action = plan.ExportPlanAction(self.plan, self.delete_after,
                                       self.exports_container)
        action.run()

        self.swift.get_container.assert_has_calls(get_container_mock_calls)
        self.swift.get_object.assert_has_calls(
            get_object_mock_calls, any_order=True)
        self.mistral.environments.get.assert_called_once_with(self.plan)
        self.swift.put_object.assert_called_once()
        mock_create_tarball.assert_called_once()

    def test_run_container_does_not_exist(self):
        self.swift.get_container.side_effect = swiftexceptions.ClientException(
            self.plan)

        action = plan.ExportPlanAction(self.plan, self.delete_after,
                                       self.exports_container)
        result = action.run()

        error = "Error attempting an operation on container: %s" % self.plan
        self.assertIn(error, result.error)

    def test_run_environment_does_not_exist(self):
        self.mistral.environments.get.side_effect = mistral_base.APIException

        action = plan.ExportPlanAction(self.plan, self.delete_after,
                                       self.exports_container)
        result = action.run()

        error = "The Mistral environment %s could not be found." % self.plan
        self.assertEqual(error, result.error)

    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run_error_creating_tarball(self, mock_create_tarball):
        mock_create_tarball.side_effect = processutils.ProcessExecutionError

        action = plan.ExportPlanAction(self.plan, self.delete_after,
                                       self.exports_container)
        result = action.run()

        error = "Error while creating a tarball"
        self.assertIn(error, result.error)
