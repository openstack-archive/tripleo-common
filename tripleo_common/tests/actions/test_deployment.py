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

from tripleo_common.actions import deployment
from tripleo_common.tests import base


class DeploymentFailuresActionTest(base.TestCase):

    def setUp(self):
        super(DeploymentFailuresActionTest, self).setUp()
        self.plan = 'overcloud'
        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.actions.deployment.open')
    def test_get_deployment_failures(self, mock_open):

        test_result = dict(host0=["a", "b", "c"])
        mock_read = mock.MagicMock()
        mock_read.read.return_value = json.dumps(test_result)
        mock_open.return_value = mock_read

        action = deployment.DeploymentFailuresAction(self.plan)
        result = action.run(self.ctx)

        self.assertEqual(result['failures'], test_result)

    @mock.patch('tripleo_common.actions.deployment.open')
    def test_get_deployment_failures_no_file(self, mock_open):

        mock_open.side_effect = IOError()

        action = deployment.DeploymentFailuresAction(self.plan)
        result = action.run(self.ctx)

        self.assertTrue(result['message'].startswith(
                        "Ansible errors file not found at"))
        self.assertEqual({}, result['failures'])
