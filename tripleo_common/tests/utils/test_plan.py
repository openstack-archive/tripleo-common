# Copyright (c) 2017 Red Hat, Inc.
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

import json
import mock
import os

from swiftclient import exceptions as swiftexceptions

from tripleo_common.tests import base
from tripleo_common.utils import plan as plan_utils


PLAN_ENV_CONTENTS = """
version: 1.0

name: overcloud
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

USER_ENV_CONTENTS = """
resource_registry:
  OS::TripleO::Foo: bar.yaml
"""

UNORDERED_PLAN_ENV_LIST = [
    {'path': 'overcloud-resource-registry-puppet.yaml'},
    {'path': 'environments/docker-ha.yaml'},
    {'path': 'environments/custom-environment-not-in-capabilities-map.yaml'},
    {'path': 'environments/containers-default-parameters.yaml'},
    {'path': 'environments/docker.yaml'}
]

CAPABILITIES_DICT = {
    'topics': [{
        'environment_groups': [{
            'environments': [{
                'file': 'overcloud-resource-registry-puppet.yaml'}
            ]}, {
            'environments': [{
                'file': 'environments/docker.yaml',
                'requires': ['overcloud-resource-registry-puppet.yaml']
            }, {
                'file': 'environments/containers-default-parameters.yaml',
                'requires': ['overcloud-resource-registry-puppet.yaml',
                             'environments/docker.yaml']
            }]}, {
            'environments': [{
                'file': 'environments/docker-ha.yaml',
                'requires': ['overcloud-resource-registry-puppet.yaml',
                             'environments/docker.yaml']
            }]}
        ]
    }]
}


class PlanTest(base.TestCase):
    def setUp(self):
        super(PlanTest, self).setUp()
        self.container = 'overcloud'
        self.swift = mock.MagicMock()
        self.swift.get_object.return_value = ({}, PLAN_ENV_CONTENTS)

    def test_get_env(self):
        env = plan_utils.get_env(self.swift, self.container)

        self.swift.get_object.assert_called()
        self.assertEqual(env['template'], 'overcloud.yaml')

    def test_get_env_not_found(self):
        self.swift.get_object.side_effect = swiftexceptions.ClientException

        self. assertRaises(Exception, plan_utils.get_env, self.swift,
                           self.container)

    def test_get_user_env(self):
        self.swift.get_object.return_value = ({}, USER_ENV_CONTENTS)
        env = plan_utils.get_user_env(self.swift, self.container)

        self.swift.get_object.assert_called_with(
            self.container, 'user-environment.yaml')
        self.assertEqual(
            env['resource_registry']['OS::TripleO::Foo'], 'bar.yaml')

    def test_put_user_env(self):
        contents = {'a': 'b'}
        plan_utils.put_user_env(self.swift, self.container, contents)

        self.swift.put_object.assert_called_with(
            self.container, 'user-environment.yaml', 'a: b\n')

    def test_update_in_env(self):
        env = plan_utils.get_env(self.swift, self.container)

        updated_env = plan_utils.update_in_env(
            self.swift,
            env,
            'template',
            'updated-overcloud.yaml'
        )
        self.assertEqual(updated_env['template'], 'updated-overcloud.yaml')

        updated_env = plan_utils.update_in_env(
            self.swift,
            env,
            'parameter_defaults',
            {'another-key': 'another-value'}
        )
        self.assertEqual(updated_env['parameter_defaults'], {
            'BlockStorageCount': 42,
            'OvercloudControlFlavor': 'yummy',
            'another-key': 'another-value'
        })

        updated_env = plan_utils.update_in_env(
            self.swift,
            env,
            'parameter_defaults',
            delete_key=True
        )
        self.assertNotIn('parameter_defaults', updated_env)

        self.swift.get_object.assert_called()
        self.swift.put_object.assert_called()

    def test_write_json_temp_file(self):
        name = plan_utils.write_json_temp_file({'foo': 'bar'})
        with open(name) as f:
            self.assertEqual({'foo': 'bar'}, json.load(f))
        os.remove(name)

    @mock.patch('requests.request', autospec=True)
    def test_object_request(self, request):
        request.return_value.content = 'foo'

        content = plan_utils.object_request('GET', '/foo/bar', 'asdf1234')

        self.assertEqual('foo', content)
        request.assert_called_once_with(
            'GET', '/foo/bar', headers={'X-Auth-Token': 'asdf1234'})

    @mock.patch('tripleo_common.utils.plan.object_request',
                autospec=True)
    def test_process_environments_and_files(self, object_request):
        swift_url = 'https://192.0.2.1:8443/foo'
        url = '%s/bar' % swift_url
        object_request.return_value = 'parameter_defaults: {foo: bar}'
        swift = mock.Mock()
        swift.url = swift_url
        swift.token = 'asdf1234'

        result = plan_utils.process_environments_and_files(swift, [url])

        self.assertEqual(
            {'parameter_defaults': {'foo': 'bar'}},
            result[1]
        )
        object_request.assert_called_once_with(
            'GET',
            'https://192.0.2.1:8443/foo/bar',
            'asdf1234'
        )

    @mock.patch('tripleo_common.utils.plan.object_request',
                autospec=True)
    def test_get_template_contents(self, object_request):
        swift_url = 'https://192.0.2.1:8443/foo'
        url = '%s/bar' % swift_url
        object_request.return_value = 'heat_template_version: 2016-04-30'
        swift = mock.Mock()
        swift.url = swift_url
        swift.token = 'asdf1234'

        result = plan_utils.get_template_contents(swift, url)

        self.assertEqual(
            {'heat_template_version': '2016-04-30'},
            result[1]
        )
        object_request.assert_called_once_with(
            'GET',
            'https://192.0.2.1:8443/foo/bar',
            'asdf1234'
        )

    def test_build_env_paths(self):
        swift = mock.Mock()
        swift.url = 'https://192.0.2.1:8443/foo'
        swift.token = 'asdf1234'
        plan = {
            'version': '1.0',
            'environments': [
                {'path': 'bar.yaml'},
                {'data': {
                    'parameter_defaults': {'InlineParam': 1}}}
            ],
            'passwords': {
                'ThePassword': 'password1'
            },
            'derived_parameters': {
                'DerivedParam': 'DerivedValue',
                'MergableParam': {
                    'one': 'derived one',
                    'two': 'derived two',
                },
            },
            'parameter_defaults': {
                'Foo': 'bar',
                'MergableParam': {
                    'one': 'user one',
                    'three': 'user three',
                },
            },
            'resource_registry': {
                'Foo::Bar': 'foo_bar.yaml'
            },
        }

        env_paths, temp_env_paths = plan_utils.build_env_paths(
            swift, 'overcloud', plan)

        self.assertEqual(3, len(temp_env_paths))
        self.assertEqual(
            ['https://192.0.2.1:8443/foo/overcloud/bar.yaml'] + temp_env_paths,
            env_paths
        )

        with open(env_paths[1]) as f:
            self.assertEqual(
                {'parameter_defaults': {'InlineParam': 1}},
                json.load(f)
            )

        with open(env_paths[2]) as f:
            self.assertEqual(
                {'parameter_defaults': {
                    'ThePassword': 'password1',
                    'DerivedParam': 'DerivedValue',
                    'Foo': 'bar',
                    'MergableParam': {
                        'one': 'user one',
                        'two': 'derived two',
                        'three': 'user three',
                    }
                }},
                json.load(f)
            )

        with open(env_paths[3]) as f:
            self.assertEqual(
                {'resource_registry': {
                    'Foo::Bar': 'foo_bar.yaml'
                }},
                json.load(f)
            )

        for path in temp_env_paths:
            os.remove(path)

    def test_apply_env_order(self):
        ordered_plan_env_list = [
            {'path': 'overcloud-resource-registry-puppet.yaml'},
            {'path': 'environments/docker.yaml'},
            {'path': 'environments/docker-ha.yaml'},
            {'path': 'environments/containers-default-parameters.yaml'},
            {'path':
                'environments/custom-environment-not-in-capabilities-map.yaml'}
        ]

        ordered_env = plan_utils.apply_environments_order(
            CAPABILITIES_DICT, UNORDERED_PLAN_ENV_LIST)
        self.assertEqual(ordered_env, ordered_plan_env_list)
