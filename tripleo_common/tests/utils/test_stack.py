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
import tempfile
from unittest import mock

import yaml

from heatclient import exc as heat_exc
from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
from tripleo_common.tests import base
from tripleo_common.utils import stack


class DeployStackTest(base.TestCase):

    @mock.patch('tripleo_common.utils.stack.time')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_stack_deploy(
        self, mock_get_template_contents,
        mock_process_multiple_environments_and_files,
        mock_time):

        # setup swift
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': 'overcloud',
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'random_existing_data': 'a_value'},
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )
        heat = mock.MagicMock()
        heat.stacks.get.return_value = None

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        # freeze time at datetime.datetime(2016, 9, 8, 16, 24, 24)
        mock_time.time.return_value = 1473366264

        stack.deploy_stack(swift, heat, 'overcloud')

        # verify parameters are as expected
        expected_defaults = {'DeployIdentifier': 1473366264,
                             'StackAction': 'CREATE',
                             'random_existing_data': 'a_value'}

        mock_env_updated = yaml.safe_dump({
            'name': 'overcloud',
            'temp_environment': 'temp_environment',
            'parameter_defaults': expected_defaults,
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_called_once_with(
            'overcloud',
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        heat.stacks.create.assert_called_once_with(
            environment={},
            files={},
            stack_name='overcloud',
            template={'heat_template_version': '2016-04-30'},
            timeout_mins=240,
        )
        swift.delete_object.assert_called_once_with(
            "overcloud-swift-rings", "swift-rings.tar.gz")
        swift.copy_object.assert_called_once_with(
            "overcloud-swift-rings", "swift-rings.tar.gz",
            "overcloud-swift-rings/swift-rings.tar.gz-%d" % 1473366264)

    @mock.patch('tripleo_common.utils.stack.time')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_run_skip_deploy_identifier(
            self, mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_time):

        # setup swift
        swift = mock.MagicMock(url="http://test.com")

        heat = mock.MagicMock()
        heat.stacks.get.return_value = None

        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'random_existing_data': 'a_value'},
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        # freeze time at datetime.datetime(2016, 9, 8, 16, 24, 24)
        mock_time.time.return_value = 1473366264

        stack.deploy_stack(swift, heat,
                           'overcloud', skip_deploy_identifier=True)

        # verify parameters are as expected
        mock_env_updated = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'parameter_defaults': {'StackAction': 'CREATE',
                                   'DeployIdentifier': '',
                                   'random_existing_data': 'a_value'},
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_called_once_with(
            constants.DEFAULT_CONTAINER_NAME,
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        heat.stacks.create.assert_called_once_with(
            environment={},
            files={},
            stack_name='overcloud',
            template={'heat_template_version': '2016-04-30'},
            timeout_mins=240,
        )
        swift.delete_object.assert_called_once_with(
            "overcloud-swift-rings", "swift-rings.tar.gz")
        swift.copy_object.assert_called_once_with(
            "overcloud-swift-rings", "swift-rings.tar.gz",
            "overcloud-swift-rings/swift-rings.tar.gz-%d" % 1473366264)

    @mock.patch('tripleo_common.utils.stack.time')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_run_create_failed(
        self, mock_get_template_contents,
        mock_process_multiple_environments_and_files,
        mock_time):

        # setup swift
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': 'overcloud',
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'random_existing_data': 'a_value'},
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        heat = mock.MagicMock()
        heat.stacks.get.return_value = None
        heat.stacks.create.side_effect = heat_exc.HTTPException("Oops")

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        # freeze time at datetime.datetime(2016, 9, 8, 16, 24, 24)
        mock_time.time.return_value = 1473366264

        self.assertRaises(RuntimeError, stack.deploy_stack,
                          swift, heat, 'overcloud')

    @mock.patch('tripleo_common.update.check_neutron_mechanism_drivers')
    @mock.patch('tripleo_common.utils.stack.time')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_run_update_failed(
        self, mock_get_template_contents,
        mock_process_multiple_environments_and_files, mock_time,
        mock_check_neutron_drivers):

        # setup swift
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': 'overcloud',
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'random_existing_data': 'a_value'},
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        heat = mock.MagicMock()
        heat.stacks.get.return_value = mock.Mock()
        heat.stacks.update.side_effect = heat_exc.HTTPException("Oops")

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        # freeze time at datetime.datetime(2016, 9, 8, 16, 24, 24)
        mock_time.time.return_value = 1473366264
        mock_check_neutron_drivers.return_value = None

        self.assertRaises(RuntimeError, stack.deploy_stack,
                          swift, heat, 'overcloud')

    def test_set_tls_parameters_no_ca_found(self):
        my_params = {}
        my_env = {'parameter_defaults': {}}
        stack.set_tls_parameters(
            parameters=my_params, env=my_env,
            local_ca_path='/tmp/my-unexistent-file.txt')
        self.assertEqual(my_params, {})

    def test_set_tls_parameters_ca_found_no_camap_provided(self):
        my_params = {}
        my_env = {'parameter_defaults': {}}
        with tempfile.NamedTemporaryFile() as ca_file:
            # Write test data
            ca_file.write(b'FAKE CA CERT')
            ca_file.flush()

            # Test
            stack.set_tls_parameters(
                parameters=my_params, env=my_env,
                local_ca_path=ca_file.name)
            self.assertIn('CAMap', my_params)
            self.assertIn('undercloud-ca', my_params['CAMap'])
            self.assertIn('content', my_params['CAMap']['undercloud-ca'])
            self.assertEqual(
                'FAKE CA CERT',
                my_params['CAMap']['undercloud-ca']['content'])

    def test_set_tls_parameters_ca_found_camap_provided(self):
        my_params = {}
        my_env = {
            'parameter_defaults': {
                'CAMap': {'overcloud-ca': {'content': 'ANOTER FAKE CERT'}}}}
        with tempfile.NamedTemporaryFile() as ca_file:
            # Write test data
            ca_file.write(b'FAKE CA CERT')
            ca_file.flush()

            # Test
            stack.set_tls_parameters(
                parameters=my_params, env=my_env,
                local_ca_path=ca_file.name)
            self.assertIn('CAMap', my_params)
            self.assertIn('undercloud-ca', my_params['CAMap'])
            self.assertIn('content', my_params['CAMap']['undercloud-ca'])
            self.assertEqual('FAKE CA CERT',
                             my_params['CAMap']['undercloud-ca']['content'])
            self.assertIn('overcloud-ca', my_params['CAMap'])
            self.assertIn('content', my_params['CAMap']['overcloud-ca'])
            self.assertEqual('ANOTER FAKE CERT',
                             my_params['CAMap']['overcloud-ca']['content'])
