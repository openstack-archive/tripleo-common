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

import yaml

import mock
from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
from tripleo_common.tests import base
from tripleo_common.utils import stack_parameters


class StackParametersTest(base.TestCase):

    @mock.patch('tripleo_common.utils.plan.'
                'cache_delete')
    def test_reset_parameter(self, mock_cache):
        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'parameter_defaults': {'SomeTestParameter': 42}
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)

        # Test
        stack_parameters.reset_parameters(swift)

        mock_env_reset = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_called_once_with(
            constants.DEFAULT_CONTAINER_NAME,
            constants.PLAN_ENVIRONMENT,
            mock_env_reset
        )
        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get"
        )

    @mock.patch('uuid.uuid4')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.'
                'get_template_contents')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    def test_update_parameters(self, mock_cache,
                               mock_get_template_contents,
                               mock_env_files,
                               mock_uuid):

        mock_env_files.return_value = ({}, {})

        swift = mock.MagicMock(url="http://test.com")

        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }, default_flow_style=False)

        mock_roles = yaml.safe_dump([{"name": "foo"}])
        mock_network = yaml.safe_dump([{'enabled': False}])
        mock_exclude = yaml.safe_dump({"name": "foo"})

        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        def return_container_files(*args):
            return ('headers', [{'name': 'foo.role.j2.yaml'}])

        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)

        mock_heat = mock.MagicMock()

        mock_heat.stacks.validate.return_value = {
            "Type": "Foo",
            "Description": "Le foo bar",
            "Parameters": {"bar": {"foo": "bar barz"}},
            "NestedParameters": {"Type": "foobar"}
        }

        mock_uuid.return_value = "cheese"

        expected_value = {
            'environment_parameters': None,
            'heat_resource_tree': {
                'parameters': {'bar': {'foo': 'bar barz',
                                       'name': 'bar'}},
                'resources': {'cheese': {
                    'id': 'cheese',
                    'name': 'Root',
                    'description': 'Le foo bar',
                    'parameters': ['bar'],
                    'resources': ['cheese'],
                    'type': 'Foo'}
                }
            }
        }

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })

        # Test
        test_parameters = {'SomeTestParameter': 42}
        result = stack_parameters.update_parameters(
            swift, mock_heat, test_parameters)

        mock_env_updated = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'parameter_defaults': {'SomeTestParameter': 42},
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_any_call(
            constants.DEFAULT_CONTAINER_NAME,
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        mock_heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )

        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get",
            expected_value
        )
        self.assertEqual(result, expected_value)

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.'
                'get_template_contents')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    def test_update_parameter_new_key(self, mock_cache,
                                      mock_get_template_contents,
                                      mock_env_files):

        mock_env_files.return_value = ({}, {})

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }, default_flow_style=False)

        mock_roles = yaml.safe_dump([{"name": "foo"}])
        mock_network = yaml.safe_dump([{'enabled': False}])
        mock_exclude = yaml.safe_dump({"name": "foo"})

        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        def return_container_files(*args):
            return ('headers', [{'name': 'foo.role.j2.yaml'}])

        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)

        heat = mock.MagicMock()
        heat.stacks.validate.return_value = {}

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })

        # Test
        test_parameters = {'SomeTestParameter': 42}
        stack_parameters.update_parameters(
            swift, heat, test_parameters,
            parameter_key='test_key')
        mock_env_updated = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'test_key': {'SomeTestParameter': 42},
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}]
        }, default_flow_style=False)

        swift.put_object.assert_any_call(
            constants.DEFAULT_CONTAINER_NAME,
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )

        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get",
            {'environment_parameters': None, 'heat_resource_tree': {}}
        )

    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.'
                'get_template_contents')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.parameters.set_count_and_flavor_params')
    def test_update_role_parameter(self, mock_set_count_and_flavor,
                                   mock_cache, mock_get_template_contents,
                                   mock_env_files):

        mock_env_files.return_value = ({}, {})

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': 'overcast'
        }, default_flow_style=False)

        mock_roles = yaml.safe_dump([{"name": "foo"}])
        mock_network = yaml.safe_dump([{'enabled': False}])
        mock_exclude = yaml.safe_dump({"name": "foo"})

        swift.get_object.side_effect = (
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_env),
            ({}, mock_roles),
            ({}, mock_network),
            ({}, mock_exclude),
            ({}, mock_env),
            ({}, mock_env),
            swiftexceptions.ClientException('atest2')
        )

        def return_container_files(*args):
            return ('headers', [{'name': 'foo.yaml'}])

        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)

        heat = mock.MagicMock()
        ironic = mock.MagicMock()
        compute = mock.MagicMock()

        heat.stacks.validate.return_value = {}

        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })

        params = {'CephStorageCount': 1,
                  'OvercloudCephStorageFlavor': 'ceph-storage'}
        mock_set_count_and_flavor.return_value = params

        stack_parameters.update_role_parameters(
            swift, heat, ironic, compute,
            'ceph-storage', 'overcast')
        mock_env_updated = yaml.safe_dump({
            'name': 'overcast',
            'parameter_defaults': params
        }, default_flow_style=False)

        swift.put_object.assert_any_call(
            'overcast',
            constants.PLAN_ENVIRONMENT,
            mock_env_updated
        )

        heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )

        mock_cache.assert_called_once_with(
            swift,
            "overcast",
            "tripleo.parameters.get",
            {'environment_parameters': None, 'heat_resource_tree': {}}
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_empty_resource_tree(self,
                                 mock_get_template_contents,
                                 mock_process_multiple_environments_and_files,
                                 mock_cache_get,
                                 mock_cache_set):

        mock_cache_get.return_value = None
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
        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.validate.return_value = {}

        expected_value = {
            'heat_resource_tree': {},
            'environment_parameters': None,
        }

        # Test
        result = stack_parameters.get_flattened_parameters(swift, mock_heat)
        mock_heat.stacks.validate.assert_called_once_with(
            environment={},
            files={},
            show_nested=True,
            template={'heat_template_version': '2016-04-30'},
        )
        self.assertEqual(result, expected_value)

    @mock.patch('tripleo_common.utils.plan.'
                'cache_set')
    @mock.patch('tripleo_common.utils.plan.'
                'cache_get')
    @mock.patch('uuid.uuid4', side_effect=['1', '2'])
    @mock.patch('heatclient.common.template_utils.'
                'process_multiple_environments_and_files')
    @mock.patch('heatclient.common.template_utils.get_template_contents')
    def test_valid_resource_tree(self,
                                 mock_get_template_contents,
                                 mock_process_multiple_environments_and_files,
                                 mock_uuid,
                                 mock_cache_get,
                                 mock_cache_set):

        mock_cache_get.return_value = None
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
        mock_get_template_contents.return_value = ({}, {
            'heat_template_version': '2016-04-30'
        })
        mock_process_multiple_environments_and_files.return_value = ({}, {})

        mock_heat = mock.MagicMock()
        mock_heat.stacks.validate.return_value = {
            'NestedParameters': {
                'CephStorageHostsDeployment': {
                    'Type': 'OS::Heat::StructuredDeployments',
                },
            },
            'description': 'sample',
            'Parameters': {
                'ControllerCount': {
                    'Default': 1,
                    'Type': 'Number',
                },
            }
        }

        expected_value = {
            'heat_resource_tree': {
                'resources': {
                    '1': {
                        'id': '1',
                        'name': 'Root',
                        'resources': [
                            '2'
                        ],
                        'parameters': [
                            'ControllerCount'
                        ]
                    },
                    '2': {
                        'id': '2',
                        'name': 'CephStorageHostsDeployment',
                        'type': 'OS::Heat::StructuredDeployments'
                    }
                },
                'parameters': {
                    'ControllerCount': {
                        'default': 1,
                        'type': 'Number',
                        'name': 'ControllerCount'
                    }
                },
            },
            'environment_parameters': None,
        }

        # Test
        result = stack_parameters.get_flattened_parameters(swift, mock_heat)
        self.assertEqual(result, expected_value)
