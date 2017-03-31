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

import mock

from swiftclient import exceptions as swiftexceptions

from tripleo_common.tests import base
from tripleo_common.utils import plan as plan_utils


YAML_CONTENTS = """
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


class PlanTest(base.TestCase):
    def setUp(self):
        super(PlanTest, self).setUp()
        self.container = 'overcloud'
        self.swift = mock.MagicMock()
        self.swift.get_object.return_value = ({}, YAML_CONTENTS)

    def test_get_env(self):
        env = plan_utils.get_env(self.swift, self.container)

        self.swift.get_object.assert_called()
        self.assertEqual(env['template'], 'overcloud.yaml')

    def test_get_env_not_found(self):
        self.swift.get_object.side_effect = swiftexceptions.ClientException

        self. assertRaises(Exception, plan_utils.get_env, self.swift,
                           self.container)

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
