# Copyright 2015 Red Hat, Inc.
# All Rights Reserved.
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
import mock

from heatclient import exc as heatexceptions
from swiftclient import exceptions as swiftexceptions

from tripleo_common.core import exception
from tripleo_common.core import models
from tripleo_common.core import plan
from tripleo_common.tests import base


class PlanManagerTest(base.TestCase):

    def setUp(self):
        super(PlanManagerTest, self).setUp()
        self.heatclient = mock.MagicMock()
        self.plan_store = mock.MagicMock()
        self.plan_name = "overcloud"
        self.stack = mock.MagicMock(
            id='123',
            status='CREATE_COMPLETE',
            stack_name=self.plan_name
        )

        self.expected_plan = models.Plan(self.plan_name)
        self.expected_plan.metadata = {
            'x-container-meta-usage-tripleo': 'plan',
        }
        self.expected_plan.files = {
            'some-environment.yaml': {
                'contents': "some fake contents",
                'meta': {'file-type': 'environment'}
            },
            'some-root-environment.yaml': {
                'contents': "parameters:\n"
                            "  one: uno\n"
                            "  obj:\n"
                            "    two: due\n"
                            "    three: tre\n",
                'meta': {
                    'file-type': 'root-environment',
                    'enabled': 'True'
                }
            },
            'some-root-template.yaml': {
                'contents': "some fake contents",
                'meta': {'file-type': 'root-template'}
            },
            'some-template.yaml': {
                'contents': "some fake contents",
            },
        }

    def test_create_plan(self):
        self.plan_store.create = mock.MagicMock()
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        plan_mgr.create_plan(self.plan_name, self.expected_plan.files)
        self.plan_store.create.assert_called_with(self.plan_name)
        # calls the Exception handling in create_plan
        with mock.patch('tripleo_common.core.plan.LOG') as log_mock:
            self.plan_store.create = mock.Mock(side_effect=ValueError())
            self.assertRaises(ValueError,
                              plan_mgr.create_plan,
                              self.plan_name, self.expected_plan.files)
            log_mock.exception.assert_called_with("Error creating plan.")

    def test_delete_plan(self):
        # test that stack exists
        self.heatclient.stacks.get = mock.MagicMock(return_value=self.stack)
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        self.assertRaises(exception.StackInUseError,
                          plan_mgr.delete_plan,
                          self.plan_name)
        self.heatclient.stacks.get.assert_called_with(self.plan_name)

        # test that stack doesn't exist yet
        self.plan_store.delete = mock.MagicMock()
        self.heatclient.stacks.get = mock.Mock(
            side_effect=heatexceptions.HTTPNotFound)
        plan_mgr.delete_plan(self.plan_name)
        self.plan_store.delete.assert_called_with(self.plan_name)

        # set side effect of swiftexceptions.ClientException
        with mock.patch('tripleo_common.core.plan.LOG') as log_mock:
            self.plan_store.delete = mock.Mock(
                side_effect=swiftexceptions.ClientException(
                    "test-error", http_status=404))
            self.assertRaises(exception.PlanDoesNotExistError,
                              plan_mgr.delete_plan,
                              self.plan_name)
            log_mock.exception.assert_called_with('Swift error deleting plan.')

        # set side effect of random Exception
        self.heatclient.stacks.get = mock.Mock(
            side_effect=ValueError())
        self.assertRaises(ValueError,
                          plan_mgr.delete_plan,
                          self.plan_name)

    def test_delete_files(self):
        self.plan_store.delete_file = mock.MagicMock()
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        plan_mgr.delete_file(self.plan_name, 'fake-file.yaml')
        self.plan_store.delete_file.assert_called_with(
            self.plan_name, 'fake-file.yaml')

        self.plan_store.delete_file = mock.Mock(
            side_effect=exception.FileDoesNotExistError(name='fake-file.yaml'))
        self.assertRaises(exception.FileDoesNotExistError,
                          plan_mgr.delete_file, self.plan_name,
                          'fake-file.yaml')

        with mock.patch('tripleo_common.core.plan.LOG') as log_mock:
            self.plan_store.delete_file = mock.Mock(side_effect=ValueError())
            self.assertRaises(ValueError, plan_mgr.delete_file,
                              self.plan_name, 'fake-file.yaml')
            log_mock.exception.assert_called_with(
                "Error deleting file from plan.")

    def test_delete_temporary_environment(self):

        self.expected_plan.files = {
            'some-name.yaml': {
                'contents': "some fake contents",
                'meta': {'file-type': 'temp-environment'}
            },
        }
        self.plan_store.get = mock.MagicMock(return_value=self.expected_plan)
        self.plan_store.delete_file = mock.MagicMock()
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        plan_mgr.delete_temporary_environment(self.plan_name)
        self.plan_store.delete_file.assert_called_with(
            self.plan_name, 'some-name.yaml')

    def test_get_plan(self):
        self.expected_plan.files = {
            'some-name.yaml': {
                'contents': "some fake contents",
                'meta': {'file-type': 'environment'}
            },
        }
        self.plan_store.get = mock.MagicMock(return_value=self.expected_plan)
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        self.assertEqual(self.expected_plan,
                         plan_mgr.get_plan(self.plan_name),
                         "Plan mismatch")
        self.plan_store.get.assert_called_with(self.plan_name)
        with mock.patch('tripleo_common.core.plan.LOG') as log_mock:
            # test swift container doesn't exist
            self.plan_store.get = mock.Mock(
                side_effect=swiftexceptions.ClientException(
                    "test-error", http_status=404))
            self.assertRaises(exception.PlanDoesNotExistError,
                              plan_mgr.get_plan,
                              self.plan_name)
            log_mock.exception.assert_called_with(
                'Swift error retrieving plan.')

            # test other exception occurs
            self.plan_store.get = mock.Mock(side_effect=ValueError())
            self.assertRaises(ValueError, plan_mgr.get_plan, 'overcloud')
            log_mock.exception.assert_called_with("Error retrieving plan.")

    def test_get_plan_list(self):
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        self.plan_store.list = mock.MagicMock(return_value=['overcloud'])
        self.assertEqual(['overcloud'], plan_mgr.get_plan_list(),
                         "get_plan_list failed")
        with mock.patch('tripleo_common.core.plan.LOG') as log_mock:
            self.plan_store.list = mock.Mock(side_effect=ValueError())
            self.assertRaises(ValueError, plan_mgr.get_plan_list)
            log_mock.exception.assert_called_with(
                "Error retrieving plan list.")

    def test_get_deployment_parameters(self):
        self.plan_store.get = mock.MagicMock(return_value=self.expected_plan)
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        with mock.patch('tripleo_common.utils.templates') as templates:
            templates.process_plan_data.return_value = (
                "some fake contents", {
                    'parameters': {
                        'obj': {
                            'two': 'due',
                            'three': 'tre'
                        },
                        'one': 'uno'
                    }
                }, {'some-template.yaml': 'some fake contents'})
            self.heatclient.stacks.validate = mock.MagicMock(
                return_value={
                    'parameters': {
                        'obj': {
                            'two': 'due',
                            'three': 'tre'
                        },
                        'one': 'uno'
                    }
                })
            self.assertEqual({
                'parameters': {
                    'obj': {
                        'two': 'due',
                        'three': 'tre'
                    },
                    'one': 'uno'
                }
            },
                plan_mgr.get_deployment_parameters(self.plan_name),
                "Bad params")
            self.heatclient.stacks.validate.assert_called_with(
                template="some fake contents",
                files={'some-template.yaml': 'some fake contents'},
                environment={
                    'parameters': {
                        'obj': {
                            'two': 'due',
                            'three': 'tre'
                        },
                        'one': 'uno'
                    }
                },
                show_nested=True
            )

            # set side effect of heatexceptions.HTTPBadRequest on validate
            self.heatclient.stacks.validate = mock.Mock(
                side_effect=heatexceptions.HTTPBadRequest
            )

            self.assertRaises(exception.HeatValidationFailedError,
                              plan_mgr.get_deployment_parameters,
                              self.plan_name)

    def test_update_deployment_parameters(self):
        self.plan_store.get = mock.MagicMock(return_value=self.expected_plan)
        # calls templates.process_plan_data(plan.files)
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        self.expected_plan.files['environments/deployment_parameters.yaml'] = {
            'contents':
                "parameters:\n"
                "  one: uno\n"
                "  obj:\n"
                "    two: due\n"
                "    three: tre\n",
            'meta': {'file-type': 'temp-environment'}
        }
        with mock.patch('tripleo_common.utils.templates') as templates:
            templates.process_plan_data.return_value = (
                "some fake contents", {
                    'parameters': {
                        'obj': {
                            'two': 'due',
                            'three': 'tre'
                        },
                        'one': 'uno'
                    }
                }, {'some-template.yaml': 'some fake contents'})
            self.heatclient.stacks.validate = mock.MagicMock()
            plan_mgr.validate_plan(self.plan_name)
            self.heatclient.stacks.validate.assert_called_with(
                template="some fake contents",
                files={'some-template.yaml': 'some fake contents'},
                environment={
                    'parameters': {
                        'obj': {
                            'two': 'due',
                            'three': 'tre'
                        },
                        'one': 'uno'
                    }
                },
                show_nested=True
            )
            # set side effect of heatexceptions.HTTPBadRequest on validate
            self.heatclient.stacks.validate = mock.Mock(
                side_effect=heatexceptions.HTTPBadRequest
            )

            self.assertRaises(exception.HeatValidationFailedError,
                              plan_mgr.get_deployment_parameters,
                              self.plan_name)

    def test_update_plan(self):
        self.plan_store.update = mock.MagicMock()
        self.plan_store.get = mock.MagicMock(return_value=self.expected_plan)
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        self.assertEqual(self.expected_plan,
                         plan_mgr.update_plan(
                             self.plan_name, self.expected_plan.files),
                         "Plan mismatch")
        self.plan_store.get.assert_called_with(self.plan_name)
        with mock.patch('tripleo_common.core.plan.LOG') as log_mock:
            # test swift container doesn't exist
            self.plan_store.update = mock.Mock(
                side_effect=swiftexceptions.ClientException(
                    "test-error", http_status=404))
            self.assertRaises(exception.PlanDoesNotExistError,
                              plan_mgr.update_plan,
                              self.plan_name,
                              self.expected_plan.files)
            log_mock.exception.assert_called_with(
                'Swift error updating plan.')

            # test other exception occurs
            self.plan_store.update = mock.Mock(side_effect=ValueError())
            self.assertRaises(ValueError, plan_mgr.update_plan,
                              self.plan_name, self.expected_plan.files)
            log_mock.exception.assert_called_with("Error updating plan.")

    def test_validate_plan(self):
        # calls self.get_plan(plan_name)
        self.plan_store.get = mock.MagicMock(return_value=self.expected_plan)
        # test 2 root-templates to get exception.TooManyRootTemplatesError
        self.expected_plan.files['another-root-template.yaml'] = {
            'contents': "some fake contents",
            'meta': {'file-type': 'root-template'}
        }
        plan_mgr = plan.PlanManager(self.plan_store, self.heatclient)
        self.assertRaises(exception.TooManyRootTemplatesError,
                          plan_mgr.validate_plan,
                          self.plan_name)
        del(self.expected_plan.files['another-root-template.yaml'])
        # calls templates.process_plan_data(plan.files) (mock and assert_call)
        with mock.patch('tripleo_common.utils.templates') as templates:
            templates.process_plan_data = mock.MagicMock(return_value=(
                "some fake contents", {
                    'parameters': {
                        'obj': {
                            'two': 'due',
                            'three': 'tre'
                        },
                        'one': 'uno'
                    }
                }, {'some-template.yaml': 'some fake contents'}))
            self.heatclient.stacks.validate = mock.MagicMock()
            plan_mgr.validate_plan(self.plan_name)
            self.heatclient.stacks.validate.assert_called_with(
                template="some fake contents",
                files={'some-template.yaml': 'some fake contents'},
                environment={
                    'parameters': {
                        'obj': {
                            'two': 'due',
                            'three': 'tre'
                        },
                        'one': 'uno'
                    }
                },
                show_nested=True
            )
            # set side effect of heatexceptions.HTTPBadRequest on validate
            self.heatclient.stacks.validate = mock.Mock(
                side_effect=heatexceptions.HTTPBadRequest
            )
            with mock.patch('tripleo_common.core.plan.LOG') as log_mock:
                self.assertRaises(exception.HeatValidationFailedError,
                                  plan_mgr.validate_plan,
                                  self.plan_name)
                log_mock.exception.assert_called_with(
                    "Error validating the plan.")
