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

from heatclient import exc as heatexceptions
from mistral_lib import actions
from oslo_concurrency import processutils
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import plan
from tripleo_common import exception
from tripleo_common.tests import base


ENV_YAML_CONTENTS = """
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


class CreateContainerActionTest(base.TestCase):

    def setUp(self):
        super(CreateContainerActionTest, self).setUp()
        # A container that name enforces all validation rules
        self.container_name = 'Test-container-7'
        self.expected_list = ['', [{'name': 'test1'}, {'name': 'test2'}]]
        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, get_obj_client_mock):

        # Setup
        swift = mock.MagicMock()
        swift.get_account.return_value = self.expected_list
        get_obj_client_mock.return_value = swift

        # Test
        action = plan.CreateContainerAction(self.container_name)
        action.run(self.ctx)

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
        result = action.run(self.ctx)

        error_str = ('A container with the name %s already'
                     ' exists.') % self.container_name
        self.assertEqual(result, actions.Result(
            None, error_str))

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_invalid_name(self, get_obj_client_mock):
        # Setup
        swift = mock.MagicMock()
        get_obj_client_mock.return_value = swift

        # Test
        action = plan.CreateContainerAction("invalid_underscore")
        result = action.run(self.ctx)

        error_str = ("Unable to create plan. The plan name must only contain "
                     "letters, numbers or dashes")
        self.assertEqual(result, actions.Result(
            None, error_str))


class ListPlansActionTest(base.TestCase):

    def setUp(self):
        super(ListPlansActionTest, self).setUp()
        self.container = 'overcloud'
        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, get_obj_client_mock):

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

        # Test
        action = plan.ListPlansAction()
        action.run(self.ctx)

        # verify
        self.assertEqual([self.container], action.run(self.ctx))
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
        self.ctx = mock.MagicMock()

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_orchestration_client')
    def test_run_stack_exists(self, get_orchestration_client):

        # setup heat
        heat = mock.MagicMock()
        heat.stacks.get.return_value = self.stack
        get_orchestration_client.return_value = heat

        # test that stack exists
        action = plan.DeletePlanAction(self.container_name)
        self.assertRaises(exception.StackInUseError, action.run, self.ctx)
        heat.stacks.get.assert_called_with(self.container_name)

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_orchestration_client')
    def test_run(self, get_orchestration_client, get_obj_client_mock):

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

        # setup heat
        heat = mock.MagicMock()
        heat.stacks.get = mock.Mock(
            side_effect=heatexceptions.HTTPNotFound)
        get_orchestration_client.return_value = heat

        action = plan.DeletePlanAction(self.container_name)
        action.run(self.ctx)

        mock_calls = [
            mock.call('overcloud', 'some-name.yaml'),
            mock.call('overcloud', 'some-other-name.yaml'),
            mock.call('overcloud', 'yet-some-other-name.yaml'),
            mock.call('overcloud', 'finally-another-name.yaml')
        ]
        swift.delete_object.assert_has_calls(
            mock_calls, any_order=True)

        swift.delete_container.assert_called_with(self.container_name)


class RoleListActionTest(base.TestCase):

    def setUp(self):
        super(RoleListActionTest, self).setUp()
        self.container = 'overcloud'
        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, get_obj_client_mock):
        # setup swift
        swift = mock.MagicMock()
        swift.get_object.return_value = ({}, ROLES_DATA_YAML_CONTENTS)
        get_obj_client_mock.return_value = swift

        # Test
        action = plan.ListRolesAction()
        result = action.run(self.ctx)

        # verify
        expected = ['MyController', 'Compute', 'CustomRole']
        self.assertEqual(expected, result)

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_no_roles_data_file(self, get_obj_client_mock):

        swift = mock.MagicMock()
        swift.get_object.side_effect = swiftexceptions.ClientException("404")
        get_obj_client_mock.return_value = swift

        action = plan.ListRolesAction()
        result = action.run(self.ctx)

        error_str = ('Error retrieving roles data from deployment plan: 404')
        self.assertEqual(result.error, error_str)


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

        self.ctx = mock.MagicMock()

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
        action.run(self.ctx)

        self.swift.get_container.assert_has_calls(get_container_mock_calls)
        self.swift.get_object.assert_has_calls(
            get_object_mock_calls, any_order=True)
        self.swift.put_object.assert_called_once()
        mock_create_tarball.assert_called_once()

    def test_run_container_does_not_exist(self):
        self.swift.get_container.side_effect = swiftexceptions.ClientException(
            self.plan)

        action = plan.ExportPlanAction(self.plan, self.delete_after,
                                       self.exports_container)
        result = action.run(self.ctx)

        error = "Error attempting an operation on container: %s" % self.plan
        self.assertIn(error, result.error)

    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run_error_creating_tarball(self, mock_create_tarball):
        mock_create_tarball.side_effect = processutils.ProcessExecutionError

        action = plan.ExportPlanAction(self.plan, self.delete_after,
                                       self.exports_container)
        result = action.run(self.ctx)

        error = "Error while creating a tarball"
        self.assertIn(error, result.error)
