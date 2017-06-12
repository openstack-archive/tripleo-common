# Copyright 2017 Red Hat, Inc.
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
import os

from oslo_concurrency import processutils

from tripleo_common.actions import ansible
from tripleo_common.tests import base


class AnsibleActionTest(base.TestCase):

    def setUp(self):
        super(AnsibleActionTest, self).setUp()

        self.hosts = "127.0.0.2"
        self.module = "foo"
        self.remote_user = 'fido'
        self.become = True
        self.become_user = 'root'
        self.ctx = mock.MagicMock()

    @mock.patch("oslo_concurrency.processutils.execute")
    def test_run(self, mock_execute):

        mock_execute.return_value = ('', '')

        action = ansible.AnsibleAction(
            hosts=self.hosts, module=self.module, remote_user=self.remote_user,
            become=self.become, become_user=self.become_user)
        action.run(self.ctx)

        mock_execute.assert_called_once_with(
            'ansible', self.hosts, '-vvvvv', '--module-name',
            self.module, '--user', self.remote_user, '--become',
            '--become-user', self.become_user,
            log_errors=processutils.LogErrors.ALL
        )


class AnsiblePlaybookActionTest(base.TestCase):

    def setUp(self):
        super(AnsiblePlaybookActionTest, self).setUp()

        self.playbook = "myplaybook"
        self.limit_hosts = None
        self.remote_user = 'fido'
        self.become = True
        self.become_user = 'root'
        self.extra_vars = {"var1": True, "var2": 0}
        self.verbosity = 1
        self.ctx = mock.MagicMock()

    @mock.patch("oslo_concurrency.processutils.execute")
    def test_run(self, mock_execute):

        mock_execute.return_value = ('', '')

        action = ansible.AnsiblePlaybookAction(
            playbook=self.playbook, limit_hosts=self.limit_hosts,
            remote_user=self.remote_user, become=self.become,
            become_user=self.become_user, extra_vars=self.extra_vars,
            verbosity=self.verbosity)
        action.run(self.ctx)

        pb = os.path.join(action.work_dir, 'playbook.yaml')

        mock_execute.assert_called_once_with(
            'ansible-playbook', '-v', pb, '--user',
            self.remote_user, '--become', '--become-user', self.become_user,
            '--extra-vars', json.dumps(self.extra_vars),
            log_errors=processutils.LogErrors.ALL)
