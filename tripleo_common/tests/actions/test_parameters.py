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

import yaml

from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import parameters
from tripleo_common import exception
from tripleo_common.tests import base


class GetProfileOfFlavorActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.parameters.get_profile_of_flavor')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    def test_profile_found(self, mock_get_compute_client,
                           mock_get_profile_of_flavor):
        mock_ctx = mock.MagicMock()
        mock_get_profile_of_flavor.return_value = 'compute'
        action = parameters.GetProfileOfFlavorAction('oooq_compute')
        result = action.run(mock_ctx)
        expected_result = "compute"
        self.assertEqual(result, expected_result)

    @mock.patch('tripleo_common.utils.parameters.get_profile_of_flavor')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    def test_profile_not_found(self, mock_get_compute_client,
                               mock_get_profile_of_flavor):
        mock_ctx = mock.MagicMock()
        profile = (exception.DeriveParamsError, )
        mock_get_profile_of_flavor.side_effect = profile
        action = parameters.GetProfileOfFlavorAction('no_profile')
        result = action.run(mock_ctx)
        self.assertTrue(result.is_error())
        mock_get_profile_of_flavor.assert_called_once()


class GetNetworkConfigActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_valid_network_config(
            self, mock_get_object_client, mock_get_workflow_client,
            mock_get_orchestration_client, mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_cache_get,
            mock_cache_set):

        mock_ctx = mock.MagicMock()
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            swiftexceptions.ClientException('atest2'),
            ({}, mock_env)
        )
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": "echo \'{\"network_config\": {}}\'"
                           " > /etc/os-net-config/config.json"}
            }])

        mock_get_orchestration_client.return_value = mock_heat

        mock_cache_get.return_value = None
        expected = {"network_config": {}}
        # Test
        action = parameters.GetNetworkConfigAction(container='overcloud',
                                                   role_name='Compute')
        result = action.run(mock_ctx)
        self.assertEqual(expected, result)
        mock_heat.stacks.preview.assert_called_once_with(
            environment={},
            files={},
            template={'heat_template_version': '2016-04-30'},
            stack_name='overcloud-TEMP',
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_valid_network_config_with_no_interface_routes_inputs(
            self, mock_get_object_client, mock_get_workflow_client,
            mock_get_orchestration_client, mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_cache_get,
            mock_cache_set):

        mock_ctx = mock.MagicMock()
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            swiftexceptions.ClientException('atest2'),
            ({}, mock_env)
        )
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30',
            'resources': {'ComputeGroupVars': {'properties': {
                'value': {'role_networks': ['InternalApi', 'Storage']}
                }
            }}
        })
        mock_process_multiple_environments_and_files.return_value = (
            {}, {'parameter_defaults': {}})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": "echo \'{\"network_config\": {}}\'"
                           " > /etc/os-net-config/config.json"}
            }])

        mock_get_orchestration_client.return_value = mock_heat

        mock_cache_get.return_value = None
        expected = {"network_config": {}}
        # Test
        action = parameters.GetNetworkConfigAction(container='overcloud',
                                                   role_name='Compute')
        result = action.run(mock_ctx)
        self.assertEqual(expected, result)
        mock_heat.stacks.preview.assert_called_once_with(
            environment={'parameter_defaults': {
                'InternalApiInterfaceRoutes': [[]],
                'StorageInterfaceRoutes': [[]]}},
            files={},
            template={'heat_template_version': '2016-04-30',
                      'resources': {'ComputeGroupVars': {
                          'properties': {'value': {
                              'role_networks': ['InternalApi',
                                                'Storage']}}}}},
            stack_name='overcloud-TEMP',
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_valid_network_config_with_interface_routes_inputs(
            self, mock_get_object_client, mock_get_workflow_client,
            mock_get_orchestration_client, mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_cache_get,
            mock_cache_set):

        mock_ctx = mock.MagicMock()
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            swiftexceptions.ClientException('atest2'),
            ({}, mock_env)
        )
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30',
            'resources': {'ComputeGroupVars': {'properties': {
                'value': {'role_networks': ['InternalApi', 'Storage']}}}}
        })
        mock_process_multiple_environments_and_files.return_value = (
            {}, {'parameter_defaults': {
                'InternalApiInterfaceRoutes': ['test1'],
                'StorageInterfaceRoutes': ['test2']}})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": "echo \'{\"network_config\": {}}\'"
                           " > /etc/os-net-config/config.json"}
            }])

        mock_get_orchestration_client.return_value = mock_heat

        mock_cache_get.return_value = None
        expected = {"network_config": {}}
        # Test
        action = parameters.GetNetworkConfigAction(container='overcloud',
                                                   role_name='Compute')
        result = action.run(mock_ctx)
        self.assertEqual(expected, result)
        mock_heat.stacks.preview.assert_called_once_with(
            environment={'parameter_defaults': {
                'InternalApiInterfaceRoutes': ['test1'],
                'StorageInterfaceRoutes': ['test2']}},
            files={},
            template={'heat_template_version': '2016-04-30',
                      'resources': {'ComputeGroupVars': {'properties': {
                          'value': {'role_networks': ['InternalApi',
                                                      'Storage']}}}}},
            stack_name='overcloud-TEMP',
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_workflow_client')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_invalid_network_config(
            self, mock_get_object_client,
            mock_get_workflow_client, mock_get_orchestration_client,
            mock_get_template_contents,
            mock_process_multiple_environments_and_files,
            mock_cache_get, mock_cache_set):

        mock_ctx = mock.MagicMock()
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)
        swift.get_object.side_effect = (
            ({}, mock_env),
            swiftexceptions.ClientException('atest2'),
            ({}, mock_env)
        )
        mock_get_object_client.return_value = swift

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.preview.return_value = mock.Mock(resources=[{
            "resource_identity": {"stack_name": "overcloud-TEMP-Compute-0"},
            "resource_name": "OsNetConfigImpl",
            "properties": {"config": ""}
            }])

        mock_get_orchestration_client.return_value = mock_heat

        mock_cache_get.return_value = None
        # Test
        action = parameters.GetNetworkConfigAction(container='overcloud',
                                                   role_name='Compute')
        result = action.run(mock_ctx)
        self.assertTrue(result.is_error())
        mock_heat.stacks.preview.assert_called_once_with(
            environment={},
            files={},
            template={'heat_template_version': '2016-04-30'},
            stack_name='overcloud-TEMP',
        )
