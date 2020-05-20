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
from unittest import mock

from heatclient import exc as heatexceptions
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

SAMPLE_ROLE_OBJ = {
    'HostnameFormatDefault': '%stackname%-sample-%index%',
    'ServicesDefault': ['OS::TripleO::Services::Timesync'],
    'description': 'Sample!\n',
    'name': 'sample',
    'networks': ['InternalApi']
}


SAMPLE_ROLE_2 = """
###############################################################################
# Role: sample2                                                               #
###############################################################################
- name: sample2
  description: |
    Sample2!
  networks:
    - InternalApi
  HostnameFormatDefault: '%stackname%-sample-%index%'
  ServicesDefault:
    - OS::TripleO::Services::Timesync
"""

SAMPLE_ROLE_2_OBJ = {
    'HostnameFormatDefault': '%stackname%-sample-%index%',
    'ServicesDefault': ['OS::TripleO::Services::Timesync'],
    'description': 'Sample2!\n',
    'name': 'sample2',
    'networks': ['InternalApi']
}

UPDATED_ROLE = """
###############################################################################
# Role: sample                                                                #
###############################################################################
- name: sample
  description: |
    Sample!
  networks:
    - InternalApi
    - ExternalApi
  tags:
    - primary
  HostnameFormatDefault: '%stackname%-sample-%index%'
  ServicesDefault:
    - OS::TripleO::Services::Timesync
"""

UPDATED_ROLE_OBJ = {
    'HostnameFormatDefault': '%stackname%-sample-%index%',
    'ServicesDefault': ['OS::TripleO::Services::Timesync'],
    'description': 'Sample!\n',
    'name': 'sample',
    'networks': ['InternalApi', 'ExternalApi'],
    'tags': ['primary']
}


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
        heat.stacks.get.assert_called_with(
            self.container_name, resolve_outputs=False)

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

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_service')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run_success(self,
                         mock_create_tarball,
                         mock_get_obj_service):

        get_object_mock_calls = [
            mock.call(self.plan, tf) for tf in self.template_files
        ]

        swift_service = mock.MagicMock()
        swift_service.upload.return_value = ([
            {'success': True},
        ])
        mock_get_obj_service.return_value = swift_service

        action = plan.ExportPlanAction(self.plan, self.delete_after,
                                       self.exports_container)
        action.run(self.ctx)

        self.swift.get_container.assert_called_once_with(self.plan)
        self.swift.get_object.assert_has_calls(
            get_object_mock_calls, any_order=True)
        swift_service.upload.assert_called_once()
        mock_create_tarball.assert_called_once()

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_service')
    def test_run_container_does_not_exist(self,
                                          mock_get_obj_service):

        self.swift.get_container.side_effect = swiftexceptions.ClientException(
            self.plan)

        swift_service = mock.MagicMock()
        swift_service.delete.return_value = ([
            {'success': True},
        ])
        mock_get_obj_service.return_value = swift_service

        action = plan.ExportPlanAction(self.plan, self.delete_after,
                                       self.exports_container)
        result = action.run(self.ctx)

        error = "Error attempting an operation on container: %s" % self.plan
        self.assertIn(error, result.error)

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_service')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run_error_creating_tarball(self,
                                        mock_create_tarball,
                                        mock_get_obj_service):

        mock_create_tarball.side_effect = processutils.ProcessExecutionError

        swift_service = mock.MagicMock()
        swift_service.delete.return_value = ([
            {'success': True},
        ])
        mock_get_obj_service.return_value = swift_service

        action = plan.ExportPlanAction(self.plan, self.delete_after,
                                       self.exports_container)
        result = action.run(self.ctx)

        error = "Error while creating a tarball"
        self.assertIn(error, result.error)


class ValidateRolesDataActionTest(base.TestCase):

    def setUp(self):
        super(ValidateRolesDataActionTest, self).setUp()
        self.container = 'overcloud'
        self.ctx = mock.MagicMock()

    def test_valid_roles(self):
        current_roles = [SAMPLE_ROLE_OBJ]
        requested_roles = [SAMPLE_ROLE_OBJ]
        action = plan.ValidateRolesDataAction(requested_roles, current_roles)
        result = action.run(self.ctx)
        self.assertTrue(result.data)

    def test_invalid_roles(self):
        current_roles = [SAMPLE_ROLE_2_OBJ]
        requested_roles = [SAMPLE_ROLE_OBJ, ]
        action = plan.ValidateRolesDataAction(requested_roles, current_roles)
        result = action.run(self.ctx)
        self.assertTrue(result.error)

    def test_validate_role_yaml_missing_name(self):
        role = SAMPLE_ROLE_OBJ.copy()
        del role['name']
        current_roles = [SAMPLE_ROLE_OBJ]
        requested_roles = [role, ]
        action = plan.ValidateRolesDataAction(requested_roles, current_roles)
        result = action.run(self.ctx)
        self.assertTrue(result.error)

    def test_validate_role_yaml_invalid_type(self):
        role = SAMPLE_ROLE_OBJ.copy()
        role['CountDefault'] = 'should not be a string'
        current_roles = [SAMPLE_ROLE_OBJ]
        requested_roles = [role, ]
        action = plan.ValidateRolesDataAction(requested_roles, current_roles)
        result = action.run(self.ctx)
        self.assertTrue(result.error)


class UpdateRolesActionTest(base.TestCase):

    def setUp(self):
        super(UpdateRolesActionTest, self).setUp()
        self.container = 'overcloud'
        self.ctx = mock.MagicMock()
        self.current_roles = [SAMPLE_ROLE_OBJ, SAMPLE_ROLE_2_OBJ]

    def test_no_primary_roles(self):
        updated_role = UPDATED_ROLE_OBJ.copy()
        del updated_role['tags']
        action = plan.UpdateRolesAction([updated_role],
                                        self.current_roles,
                                        True, self.container)

        self.assertRaises(exception.RoleMetadataError, action.run, self.ctx)

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_update_some_roles(self, get_obj_client_mock):
        # Setup
        swift = mock.MagicMock()
        get_obj_client_mock.return_value = swift

        action = plan.UpdateRolesAction([UPDATED_ROLE_OBJ],
                                        self.current_roles,
                                        False, self.container)
        result = action.run(self.ctx)

        self.assertEqual(result.data,
                         {'roles': [SAMPLE_ROLE_2_OBJ, UPDATED_ROLE_OBJ]})

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_update_replace_roles(self, get_obj_client_mock):
        # Setup
        swift = mock.MagicMock()
        get_obj_client_mock.return_value = swift

        action = plan.UpdateRolesAction([UPDATED_ROLE_OBJ],
                                        self.current_roles,
                                        True, self.container)
        result = action.run(self.ctx)

        self.assertEqual(result.data, {'roles': [UPDATED_ROLE_OBJ, ]})


class RemoveNoopDeployStepActionTest(base.TestCase):

    def setUp(self):
        super(RemoveNoopDeployStepActionTest, self).setUp()
        self.container = 'overcloud'
        self.ctx = mock.MagicMock()
        self.heat = mock.MagicMock()
        self.swift = mock.MagicMock()
        self.rr_before = {
            'OS::TripleO::Foo': 'bar.yaml',
            'OS::TripleO::DeploymentSteps': 'OS::Heat::None',
        }
        self.rr_after = {
            'OS::TripleO::Foo': 'bar.yaml',
        }

    @mock.patch('tripleo_common.actions.plan.plan_utils')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_orchestration_client')
    def test_roles_gathered(self, mock_orch_client, mock_obj_client,
                            mock_plan_utils):
        mock_obj_client.return_value = self.swift
        mock_orch_client.return_value = self.heat
        mock_plan_utils.get_env.return_value = {
            'name': self.container,
            'resource_registry': self.rr_before,
        }
        mock_plan_utils.get_user_env.return_value = {
            'resource_registry': self.rr_before,
        }
        action = plan.RemoveNoopDeployStepAction(self.container)
        action.run(self.ctx)

        mock_plan_utils.put_env.assert_called_with(
            self.swift,
            {
                'name': self.container,
                'resource_registry': self.rr_after,
            })
        mock_plan_utils.put_user_env.assert_called_with(
            self.swift, self.container, {'resource_registry': self.rr_after})
