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
import random
from six.moves import configparser
import shutil
import string
import sys
import tempfile
from unittest import mock

from oslo_concurrency import processutils

from tripleo_common.actions import ansible
from tripleo_common.tests import base


class AnsiblePlaybookActionTest(base.TestCase):

    def setUp(self):
        super(AnsiblePlaybookActionTest, self).setUp()

        self.playbook = "myplaybook"
        self.limit_hosts = None
        self.remote_user = 'fido'
        self.become = True
        self.become_user = 'root'
        self.extra_vars = {"var1": True, "var2": 0}
        self.verbosity = 2
        self.ctx = mock.MagicMock()
        self.max_message_size = 1024

    @mock.patch("tripleo_common.actions.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_run(self, mock_execute, mock_write_cfg):

        mock_execute.return_value = ('', '')

        action = ansible.AnsiblePlaybookAction(
            playbook=self.playbook, limit_hosts=self.limit_hosts,
            remote_user=self.remote_user, become=self.become,
            become_user=self.become_user, extra_vars=self.extra_vars,
            verbosity=self.verbosity, config_download_args=['--check',
                                                            '--diff'])
        ansible_config_path = os.path.join(action.work_dir, 'ansible.cfg')
        mock_write_cfg.return_value = ansible_config_path

        action.run(self.ctx)

        mock_write_cfg.assert_called_once_with(action.work_dir,
                                               self.remote_user,
                                               ssh_private_key=None,
                                               override_ansible_cfg=None)

        pb = os.path.join(action.work_dir, 'playbook.yaml')
        env = {
            'HOME': action.work_dir,
            'ANSIBLE_LOCAL_TEMP': action.work_dir,
            'ANSIBLE_CONFIG': ansible_config_path,
            'ANSIBLE_CALLBACK_WHITELIST':
                'tripleo_dense,tripleo_profile_tasks,tripleo_states',
            'ANSIBLE_STDOUT_CALLBACK': 'tripleo_dense',
            'PROFILE_TASKS_TASK_OUTPUT_LIMIT': '20',
        }
        python_version = sys.version_info.major
        ansible_playbook_cmd = 'ansible-playbook-{}'.format(python_version)
        mock_execute.assert_called_once_with(
            ansible_playbook_cmd, '-v', pb, '--become',
            '--become-user',
            self.become_user, '--extra-vars', json.dumps(self.extra_vars),
            '--check', '--diff', env_variables=env, cwd=action.work_dir,
            log_errors=processutils.LogErrors.ALL)

    @mock.patch("tripleo_common.actions.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_run_with_limit(self, mock_execute, mock_write_cfg):

        mock_execute.return_value = ('', '')

        action = ansible.AnsiblePlaybookAction(
            playbook=self.playbook, limit_hosts=['compute35'],
            blacklisted_hostnames=['compute21'],
            remote_user=self.remote_user, become=self.become,
            become_user=self.become_user, extra_vars=self.extra_vars,
            verbosity=self.verbosity, config_download_args=['--check',
                                                            '--diff'])
        ansible_config_path = os.path.join(action.work_dir, 'ansible.cfg')
        mock_write_cfg.return_value = ansible_config_path

        action.run(self.ctx)

        mock_write_cfg.assert_called_once_with(action.work_dir,
                                               self.remote_user,
                                               ssh_private_key=None,
                                               override_ansible_cfg=None)

        pb = os.path.join(action.work_dir, 'playbook.yaml')
        env = {
            'HOME': action.work_dir,
            'ANSIBLE_LOCAL_TEMP': action.work_dir,
            'ANSIBLE_CONFIG': ansible_config_path,
            'ANSIBLE_CALLBACK_WHITELIST':
                'tripleo_dense,tripleo_profile_tasks,tripleo_states',
            'ANSIBLE_STDOUT_CALLBACK': 'tripleo_dense',
            'PROFILE_TASKS_TASK_OUTPUT_LIMIT': '20',
        }
        python_version = sys.version_info.major
        ansible_playbook_cmd = 'ansible-playbook-{}'.format(python_version)
        mock_execute.assert_called_once_with(
            ansible_playbook_cmd, '-v', pb, '--limit', "['compute35']",
            '--become', '--become-user',
            self.become_user, '--extra-vars', json.dumps(self.extra_vars),
            '--check', '--diff', env_variables=env, cwd=action.work_dir,
            log_errors=processutils.LogErrors.ALL)

    @mock.patch("tripleo_common.actions.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_run_with_blacklist(self, mock_execute, mock_write_cfg):

        mock_execute.return_value = ('', '')

        action = ansible.AnsiblePlaybookAction(
            playbook=self.playbook, limit_hosts=None,
            blacklisted_hostnames=['compute21'],
            remote_user=self.remote_user, become=self.become,
            become_user=self.become_user, extra_vars=self.extra_vars,
            verbosity=self.verbosity, config_download_args=['--check',
                                                            '--diff'])
        ansible_config_path = os.path.join(action.work_dir, 'ansible.cfg')
        mock_write_cfg.return_value = ansible_config_path

        action.run(self.ctx)

        mock_write_cfg.assert_called_once_with(action.work_dir,
                                               self.remote_user,
                                               ssh_private_key=None,
                                               override_ansible_cfg=None)

        pb = os.path.join(action.work_dir, 'playbook.yaml')
        env = {
            'HOME': action.work_dir,
            'ANSIBLE_LOCAL_TEMP': action.work_dir,
            'ANSIBLE_CONFIG': ansible_config_path,
            'ANSIBLE_CALLBACK_WHITELIST':
                'tripleo_dense,tripleo_profile_tasks,tripleo_states',
            'ANSIBLE_STDOUT_CALLBACK': 'tripleo_dense',
            'PROFILE_TASKS_TASK_OUTPUT_LIMIT': '20',
        }
        python_version = sys.version_info.major
        ansible_playbook_cmd = 'ansible-playbook-{}'.format(python_version)
        mock_execute.assert_called_once_with(
            ansible_playbook_cmd, '-v', pb, '--limit', '!compute21',
            '--become', '--become-user', self.become_user, '--extra-vars',
            json.dumps(self.extra_vars), '--check', '--diff',
            env_variables=env, cwd=action.work_dir,
            log_errors=processutils.LogErrors.ALL)

    @mock.patch("tripleo_common.actions.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_post_message(self, mock_execute, mock_write_cfg):

        action = ansible.AnsiblePlaybookAction(
            playbook=self.playbook, limit_hosts=self.limit_hosts,
            remote_user=self.remote_user, become=self.become,
            become_user=self.become_user, extra_vars=self.extra_vars,
            verbosity=self.verbosity,
            max_message_size=self.max_message_size)
        ansible_config_path = os.path.join(action.work_dir, 'ansible.cfg')
        mock_write_cfg.return_value = ansible_config_path

        message_size = int(self.max_message_size * 0.5)

        # Message equal to max_message_size
        queue = mock.Mock()
        message = ''.join([string.ascii_letters[int(random.random() * 26)]
                          for x in range(1024)])
        action.post_message(queue, message)
        self.assertEqual(queue.post.call_count, 2)
        self.assertEqual(
            queue.post.call_args_list[0],
            mock.call(action.format_message(message[:message_size])))
        self.assertEqual(
            queue.post.call_args_list[1],
            mock.call(action.format_message(message[message_size:])))

        # Message less than max_message_size
        queue = mock.Mock()
        message = ''.join([string.ascii_letters[int(random.random() * 26)]
                           for x in range(512)])
        action.post_message(queue, message)
        self.assertEqual(queue.post.call_count, 1)
        self.assertEqual(
            queue.post.call_args_list[0],
            mock.call(action.format_message(message)))

        # Message double max_message_size
        queue = mock.Mock()
        message = ''.join([string.ascii_letters[int(random.random() * 26)]
                           for x in range(2048)])
        action.post_message(queue, message)
        self.assertEqual(queue.post.call_count, 4)
        self.assertEqual(
            queue.post.call_args_list[0],
            mock.call(action.format_message(message[:message_size])))
        self.assertEqual(
            queue.post.call_args_list[1],
            mock.call(action.format_message(
                      message[message_size:message_size * 2])))
        self.assertEqual(
            queue.post.call_args_list[2],
            mock.call(action.format_message(
                      message[message_size * 2:message_size * 3])))
        self.assertEqual(
            queue.post.call_args_list[3],
            mock.call(action.format_message(
                      message[message_size * 3:2048])))

    @mock.patch("shutil.rmtree")
    @mock.patch("tripleo_common.actions.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_work_dir_cleanup(self, mock_execute, mock_write_cfg, mock_rmtree):

        mock_execute.return_value = ('', '')

        action = ansible.AnsiblePlaybookAction(
            playbook=self.playbook, limit_hosts=self.limit_hosts,
            remote_user=self.remote_user, become=self.become,
            become_user=self.become_user, extra_vars=self.extra_vars,
            verbosity=0)

        try:
            action.run(self.ctx)
            mock_rmtree.assert_called_once_with(action.work_dir)
        finally:
            # Since we mocked the delete we need to manually cleanup.
            shutil.rmtree(action.work_dir)

    @mock.patch("shutil.rmtree")
    @mock.patch("tripleo_common.actions.ansible.write_default_ansible_cfg")
    @mock.patch("oslo_concurrency.processutils.execute")
    def test_work_dir_no_cleanup(self, mock_execute, mock_write_cfg,
                                 mock_rmtree):

        mock_execute.return_value = ('', '')

        # Specity a work_dir, this should not be deleted automatically.
        work_dir = tempfile.mkdtemp()
        try:
            action = ansible.AnsiblePlaybookAction(
                playbook=self.playbook, limit_hosts=self.limit_hosts,
                remote_user=self.remote_user, become=self.become,
                become_user=self.become_user, extra_vars=self.extra_vars,
                verbosity=self.verbosity, work_dir=work_dir)

            action.run(self.ctx)

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
                work_dir, None, None, None, base_ansible_cfg=ansible_cfg_path,
                override_ansible_cfg=override_ansible_cfg)

            ansible_cfg = configparser.ConfigParser()
            ansible_cfg.read(resulting_ansible_config)

            self.assertEqual('16', ansible_cfg.get('defaults', 'forks'))
