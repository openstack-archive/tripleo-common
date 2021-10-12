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
import os
import configparser
import shutil
import tempfile
from unittest import mock

from oslo_concurrency import processutils

from tripleo_common.utils import ansible
from tripleo_common.tests import base


class AnsiblePlaybookTest(base.TestCase):

    def setUp(self):
        super(AnsiblePlaybookTest, self).setUp()

        self.limit_hosts = None
        self.remote_user = 'fido'
        self.become = True
        self.become_user = 'root'
        self.extra_vars = {"var1": True, "var2": 0}
        self.verbosity = 2
        self.ctx = mock.MagicMock()
        self.max_message_size = 1024
        self.work_dir = tempfile.mkdtemp('tripleo-ansible')
        self.playbook = os.path.join(self.work_dir, "playbook.yaml")

    @mock.patch('tempfile.mkdtemp')
    @mock.patch("tripleo_common.utils.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_run(self, mock_execute, mock_write_cfg, mock_work_dir):

        mock_execute.return_value = ('', '')
        mock_work_dir.return_value = self.work_dir
        ansible_config_path = os.path.join(self.work_dir,
                                           'ansible.cfg')
        mock_write_cfg.return_value = ansible_config_path
        ansible.run_ansible_playbook(
            playbook=self.playbook, limit_hosts=self.limit_hosts,
            remote_user=self.remote_user, become=self.become,
            become_user=self.become_user, extra_vars=self.extra_vars,
            verbosity=self.verbosity)

        mock_write_cfg.assert_called_once_with(self.work_dir,
                                               self.remote_user,
                                               ssh_private_key=None,
                                               override_ansible_cfg=None)

        pb = os.path.join(self.work_dir, 'playbook.yaml')
        env = {
            'HOME': self.work_dir,
            'ANSIBLE_LOCAL_TEMP': self.work_dir,
            'ANSIBLE_CONFIG': ansible_config_path,
            'ANSIBLE_CALLBACK_WHITELIST':
                'tripleo_dense,tripleo_profile_tasks,tripleo_states',
            'ANSIBLE_STDOUT_CALLBACK': 'tripleo_dense',
            'PROFILE_TASKS_TASK_OUTPUT_LIMIT': '20',
        }
        ansible_playbook_cmd = 'ansible-playbook'
        mock_execute.assert_called_once_with(
            ansible_playbook_cmd, '-v', pb, '--become',
            '--become-user',
            self.become_user, '--extra-vars', json.dumps(self.extra_vars),
            env_variables=env, cwd=self.work_dir,
            log_errors=processutils.LogErrors.ALL)

    @mock.patch('tempfile.mkdtemp')
    @mock.patch("tripleo_common.utils.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_run_with_limit(self, mock_execute, mock_write_cfg, mock_work_dir):

        mock_execute.return_value = ('', '')
        mock_work_dir.return_value = self.work_dir
        ansible_config_path = os.path.join(self.work_dir,
                                           'ansible.cfg')
        mock_write_cfg.return_value = ansible_config_path

        ansible.run_ansible_playbook(
            playbook=self.playbook, limit_hosts=['compute35'],
            blacklisted_hostnames=['compute21'],
            remote_user=self.remote_user, become=self.become,
            become_user=self.become_user, extra_vars=self.extra_vars,
            verbosity=self.verbosity)

        mock_write_cfg.assert_called_once_with(self.work_dir,
                                               self.remote_user,
                                               ssh_private_key=None,
                                               override_ansible_cfg=None)

        pb = os.path.join(self.work_dir, 'playbook.yaml')
        env = {
            'HOME': self.work_dir,
            'ANSIBLE_LOCAL_TEMP': self.work_dir,
            'ANSIBLE_CONFIG': ansible_config_path,
            'ANSIBLE_CALLBACK_WHITELIST':
                'tripleo_dense,tripleo_profile_tasks,tripleo_states',
            'ANSIBLE_STDOUT_CALLBACK': 'tripleo_dense',
            'PROFILE_TASKS_TASK_OUTPUT_LIMIT': '20',
        }
        ansible_playbook_cmd = 'ansible-playbook'
        mock_execute.assert_called_once_with(
            ansible_playbook_cmd, '-v', pb, '--limit', "['compute35']",
            '--become', '--become-user',
            self.become_user, '--extra-vars', json.dumps(self.extra_vars),
            env_variables=env, cwd=self.work_dir,
            log_errors=processutils.LogErrors.ALL)

    @mock.patch('tempfile.mkdtemp')
    @mock.patch("shutil.rmtree")
    @mock.patch("tripleo_common.utils.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_work_dir_cleanup(self, mock_execute, mock_write_cfg,
                              mock_rmtree, mock_work_dir):

        mock_execute.return_value = ('', '')
        mock_work_dir.return_value = self.work_dir
        ansible_config_path = os.path.join(self.work_dir,
                                           'ansible.cfg')
        mock_write_cfg.return_value = ansible_config_path

        try:
            ansible.run_ansible_playbook(
                playbook=self.playbook, limit_hosts=self.limit_hosts,
                remote_user=self.remote_user, become=self.become,
                become_user=self.become_user, extra_vars=self.extra_vars,
                verbosity=0)
            mock_rmtree.assert_called_once_with(self.work_dir)
        finally:
            # Since we mocked the delete we need to manually cleanup.
            shutil.rmtree(self.work_dir)

    @mock.patch("shutil.rmtree")
    @mock.patch("tripleo_common.utils.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_work_dir_no_cleanup(self, mock_execute, mock_write_cfg,
                                 mock_rmtree):

        mock_execute.return_value = ('', '')

        # Specity a self.work_dir, this should not be deleted automatically.
        work_dir = tempfile.mkdtemp()
        ansible_config_path = os.path.join(work_dir,
                                           'ansible.cfg')
        mock_write_cfg.return_value = ansible_config_path

        try:
            ansible.run_ansible_playbook(
                playbook=self.playbook, limit_hosts=self.limit_hosts,
                remote_user=self.remote_user, become=self.become,
                become_user=self.become_user, extra_vars=self.extra_vars,
                verbosity=self.verbosity, work_dir=work_dir)

            # verify the rmtree is not called
            mock_rmtree.assert_not_called()
        finally:
            shutil.rmtree(work_dir)


class CopyConfigFileTest(base.TestCase):

    def test_copy_config_file(self):
        with tempfile.NamedTemporaryFile() as ansible_cfg_file:
            ansible_cfg_path = ansible_cfg_file.name
            work_dir = tempfile.mkdtemp(prefix='ansible-mistral-action-test')
            # Needed for the configparser to be able to read this file.
            ansible_cfg_file.write(b'[defaults]\n')
            ansible_cfg_file.write(b'[ssh_connection]\n')
            ansible_cfg_file.flush()

            resulting_ansible_config = ansible.write_default_ansible_cfg(
                work_dir, None, None, None, base_ansible_cfg=ansible_cfg_path)

            self.assertEqual(resulting_ansible_config,
                             os.path.join(work_dir, 'ansible.cfg'))

        config = configparser.ConfigParser()
        config.read(resulting_ansible_config)

        retry_files_enabled = config.get('defaults', 'retry_files_enabled')
        self.assertEqual(retry_files_enabled, 'False')

        log_path = config.get('defaults', 'log_path')
        self.assertEqual(log_path,
                         os.path.join(work_dir, 'ansible.log'))

    def test_override_ansible_cfg(self):
        with tempfile.NamedTemporaryFile() as ansible_cfg_file:
            ansible_cfg_path = ansible_cfg_file.name
            work_dir = tempfile.mkdtemp(prefix='ansible-mistral-action-test')
            # Needed for the configparser to be able to read this file.
            ansible_cfg_file.write(b'[defaults]\n')
            ansible_cfg_file.write(b'[ssh_connection]\n')
            ansible_cfg_file.flush()

            override_ansible_cfg = (
                "[defaults]\n"
                "forks=10\n"
                "[ssh_connection]\n"
                "custom_option=custom_value\n"
            )

            resulting_ansible_config = ansible.write_default_ansible_cfg(
                work_dir, None, None, None, base_ansible_cfg=ansible_cfg_path,
                override_ansible_cfg=override_ansible_cfg)

            ansible_cfg = configparser.ConfigParser()
            ansible_cfg.read(resulting_ansible_config)

            self.assertEqual('10', ansible_cfg.get('defaults', 'forks'))
            self.assertEqual('custom_value',
                             ansible_cfg.get('ssh_connection',
                                             'custom_option'))

    @mock.patch("multiprocessing.cpu_count")
    def test_override_ansible_cfg_empty(self, cpu_count):
        with tempfile.NamedTemporaryFile() as ansible_cfg_file:
            ansible_cfg_path = ansible_cfg_file.name
            work_dir = tempfile.mkdtemp(prefix='ansible-mistral-action-test')
            # Needed for the configparser to be able to read this file.
            ansible_cfg_file.write(b'[defaults]\n')
            ansible_cfg_file.write(b'[ssh_connection]\n')
            ansible_cfg_file.flush()
            cpu_count.return_value = 4
            override_ansible_cfg = ""

            resulting_ansible_config = ansible.write_default_ansible_cfg(
                work_dir, None, None, base_ansible_cfg=ansible_cfg_path,
                override_ansible_cfg=override_ansible_cfg)

            ansible_cfg = configparser.ConfigParser()
            ansible_cfg.read(resulting_ansible_config)

            self.assertEqual('16', ansible_cfg.get('defaults', 'forks'))
