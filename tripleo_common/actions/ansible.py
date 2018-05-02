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
import shutil
import six
from six.moves import configparser
import subprocess
import tempfile
import time
import yaml

from mistral_lib import actions
from oslo_concurrency import processutils

from tripleo_common.actions import base


def write_default_ansible_cfg(work_dir,
                              base_ansible_cfg='/etc/ansible/ansible.cfg'):
    ansible_config_path = os.path.join(work_dir, 'ansible.cfg')
    shutil.copy(base_ansible_cfg, ansible_config_path)

    config = configparser.ConfigParser()
    config.read(ansible_config_path)

    config.set('defaults', 'retry_files_enabled', 'False')

    with open(ansible_config_path, 'w') as configfile:
        config.write(configfile)

    return ansible_config_path


class AnsibleAction(actions.Action):
    """Executes ansible module"""

    def __init__(self, **kwargs):
        self._kwargs_for_run = kwargs
        self.hosts = self._kwargs_for_run.pop('hosts', None)
        self.module = self._kwargs_for_run.pop('module', None)
        self.module_args = self._kwargs_for_run.pop('module_args', None)
        if self.module_args:
            self.module_args = json.dumps(self.module_args)
        self.limit_hosts = self._kwargs_for_run.pop('limit_hosts', None)
        self.remote_user = self._kwargs_for_run.pop('remote_user', None)
        self.become = self._kwargs_for_run.pop('become', None)
        self.become_user = self._kwargs_for_run.pop('become_user', None)
        self.extra_vars = self._kwargs_for_run.pop('extra_vars', None)
        if self.extra_vars:
            self.extra_vars = json.dumps(self.extra_vars)
        self._inventory = self._kwargs_for_run.pop('inventory', None)
        self.verbosity = self._kwargs_for_run.pop('verbosity', 5)
        self._ssh_private_key = self._kwargs_for_run.pop(
            'ssh_private_key', None)
        self.forks = self._kwargs_for_run.pop('forks', None)
        self.timeout = self._kwargs_for_run.pop('timeout', None)
        self.ssh_extra_args = self._kwargs_for_run.pop('ssh_extra_args', None)
        if self.ssh_extra_args:
            self.ssh_extra_args = json.dumps(self.ssh_extra_args)
        self.ssh_common_args = self._kwargs_for_run.pop(
            'ssh_common_args', None)
        if self.ssh_common_args:
            self.ssh_common_args = json.dumps(self.ssh_common_args)
        self.use_openstack_credentials = self._kwargs_for_run.pop(
            'use_openstack_credentials', False)
        self.extra_env_variables = self._kwargs_for_run.pop(
            'extra_env_variables', None)

        self._work_dir = None

    @property
    def work_dir(self):
        if self._work_dir:
            return self._work_dir
        self._work_dir = tempfile.mkdtemp(prefix='ansible-mistral-action')
        return self._work_dir

    @property
    def inventory(self):
        if not self._inventory:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._inventory, six.string_types) and
                os.path.exists(self._inventory)):
            return self._inventory
        elif not isinstance(self._inventory, six.string_types):
            self._inventory = yaml.safe_dump(self._inventory)

        path = os.path.join(self.work_dir, 'inventory.yaml')

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the inventory generation failed
        with open(path, 'w') as inventory:
            inventory.write(self._inventory)

        self._inventory = path
        return path

    @property
    def ssh_private_key(self):
        if not self._ssh_private_key:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._ssh_private_key, six.string_types) and
                os.path.exists(self._ssh_private_key)):
            return self._ssh_private_key

        path = os.path.join(self.work_dir, 'ssh_private_key')

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the inventory generation failed
        with open(path, 'w') as ssh_key:
            ssh_key.write(self._ssh_private_key)
        os.chmod(path, 0o600)

        self._ssh_private_key = path
        return path

    def run(self, context):

        if 0 < self.verbosity < 6:
            verbosity_option = '-' + ('v' * self.verbosity)
            command = ['ansible', self.hosts, verbosity_option, ]
        else:
            command = ['ansible', self.hosts, ]

        if self.module:
            command.extend(['--module-name', self.module])

        if self.module_args:
            command.extend(['--args', self.module_args])

        if self.limit_hosts:
            command.extend(['--limit', self.limit_hosts])

        if self.remote_user:
            command.extend(['--user', self.remote_user])

        if self.become:
            command.extend(['--become'])

        if self.become_user:
            command.extend(['--become-user', self.become_user])

        if self.extra_vars:
            command.extend(['--extra-vars', self.extra_vars])

        if self.forks:
            command.extend(['--forks', self.forks])

        if self.ssh_common_args:
            command.extend(['--ssh-common-args', self.ssh_common_args])

        if self.ssh_extra_args:
            command.extend(['--ssh-extra-args', self.ssh_extra_args])

        if self.timeout:
            command.extend(['--timeout', self.timeout])

        if self.inventory:
            command.extend(['--inventory-file', self.inventory])

        if self.ssh_private_key:
            command.extend(['--private-key', self.ssh_private_key])

        if self.extra_env_variables:
            if not isinstance(self.extra_env_variables, dict):
                msg = "extra_env_variables must be a dict"
                return actions.Result(error=msg)

        try:
            ansible_config_path = write_default_ansible_cfg(self.work_dir)
            env_variables = {
                'HOME': self.work_dir,
                'ANSIBLE_CONFIG': ansible_config_path
            }

            if self.extra_env_variables:
                env_variables.update(self.extra_env_variables)

            if self.use_openstack_credentials:
                env_variables.update({
                    'OS_AUTH_URL': context.auth_uri,
                    'OS_USERNAME': context.user_name,
                    'OS_AUTH_TOKEN': context.auth_token,
                    'OS_PROJECT_NAME': context.project_name})

            stderr, stdout = processutils.execute(
                *command, cwd=self.work_dir,
                env_variables=env_variables,
                log_errors=processutils.LogErrors.ALL)
            return {"stderr": stderr, "stdout": stdout}
        finally:
            # NOTE(flaper87): clean the mess if debug is disabled.
            if not self.verbosity:
                shutil.rmtree(self.work_dir)


class AnsiblePlaybookAction(base.TripleOAction):
    """Executes ansible playbook"""

    def __init__(self, **kwargs):
        self._kwargs_for_run = kwargs
        self._playbook = self._kwargs_for_run.pop('playbook', None)
        self.limit_hosts = self._kwargs_for_run.pop('limit_hosts', None)
        self.module_path = self._kwargs_for_run.pop('module_path', None)
        self.remote_user = self._kwargs_for_run.pop('remote_user', None)
        self.become = self._kwargs_for_run.pop('become', None)
        self.become_user = self._kwargs_for_run.pop('become_user', None)
        self.extra_vars = self._kwargs_for_run.pop('extra_vars', None)
        if self.extra_vars:
            self.extra_vars = json.dumps(self.extra_vars)
        self._inventory = self._kwargs_for_run.pop('inventory', None)
        self.verbosity = self._kwargs_for_run.pop('verbosity', 5)
        self._ssh_private_key = self._kwargs_for_run.pop(
            'ssh_private_key', None)
        self.flush_cache = self._kwargs_for_run.pop('flush_cache', None)
        self.forks = self._kwargs_for_run.pop('forks', None)
        self.timeout = self._kwargs_for_run.pop('timeout', None)
        self.ssh_extra_args = self._kwargs_for_run.pop('ssh_extra_args', None)
        if self.ssh_extra_args:
            self.ssh_extra_args = json.dumps(self.ssh_extra_args)
        self.ssh_common_args = self._kwargs_for_run.pop(
            'ssh_common_args', None)
        if self.ssh_common_args:
            self.ssh_common_args = json.dumps(self.ssh_common_args)
        self.use_openstack_credentials = self._kwargs_for_run.pop(
            'use_openstack_credentials', False)
        self.tags = self._kwargs_for_run.pop('tags', None)
        self.skip_tags = self._kwargs_for_run.pop('skip_tags', None)
        self.extra_env_variables = self._kwargs_for_run.pop(
            'extra_env_variables', None)
        self.queue_name = self._kwargs_for_run.pop('queue_name', None)
        self.execution_id = self._kwargs_for_run.pop('execution_id', None)
        self._work_dir = self._kwargs_for_run.pop(
            'work_dir', None)
        self.max_message_size = self._kwargs_for_run.pop(
            'max_message_size', 1048576)
        self.trash_output = self._kwargs_for_run.pop('trash_output', False)

    @property
    def work_dir(self):
        if self._work_dir:
            return self._work_dir
        self._work_dir = tempfile.mkdtemp(prefix='ansible-mistral-action')
        return self._work_dir

    @property
    def inventory(self):
        if not self._inventory:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._inventory, six.string_types) and
                os.path.exists(self._inventory)):
            return self._inventory
        elif not isinstance(self._inventory, six.string_types):
            self._inventory = yaml.safe_dump(self._inventory)

        path = os.path.join(self.work_dir, 'inventory.yaml')

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the inventory generation failed
        with open(path, 'w') as inventory:
            inventory.write(self._inventory)

        self._inventory = path
        return path

    @property
    def playbook(self):
        if not self._playbook:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._playbook, six.string_types) and
                os.path.exists(self._playbook)):
            return self._playbook
        elif not isinstance(self._playbook, six.string_types):
            self._playbook = yaml.safe_dump(self._playbook)

        path = os.path.join(self.work_dir, 'playbook.yaml')

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the inventory generation failed
        with open(path, 'w') as playbook:
            playbook.write(self._playbook)

        self._playbook = path
        return path

    @property
    def ssh_private_key(self):
        if not self._ssh_private_key:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._ssh_private_key, six.string_types) and
                os.path.exists(self._ssh_private_key)):
            return self._ssh_private_key

        path = os.path.join(self.work_dir, 'ssh_private_key')

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the inventory generation failed
        with open(path, 'w') as ssh_key:
            ssh_key.write(self._ssh_private_key)
        os.chmod(path, 0o600)

        self._ssh_private_key = path
        return path

    def format_message(self, lines):
        return {
            'body': {
                'payload': {
                    'message': ''.join(lines),
                    'status': 'RUNNING',
                    'execution': {'id': self.execution_id}}}}

    def run(self, context):
        if 0 < self.verbosity < 6:
            verbosity_option = '-' + ('v' * self.verbosity)
            command = ['ansible-playbook', verbosity_option,
                       self.playbook]
        else:
            command = ['ansible-playbook', self.playbook]

        if self.limit_hosts:
            command.extend(['--limit', self.limit_hosts])

        if self.module_path:
            command.extend(['--module-path', self.module_path])

        if self.remote_user:
            command.extend(['--user', self.remote_user])

        if self.become:
            command.extend(['--become'])

        if self.become_user:
            command.extend(['--become-user', self.become_user])

        if self.extra_vars:
            command.extend(['--extra-vars', self.extra_vars])

        if self.flush_cache:
            command.extend(['--flush-cache'])

        if self.forks:
            command.extend(['--forks', self.forks])

        if self.ssh_common_args:
            command.extend(['--ssh-common-args', self.ssh_common_args])

        if self.ssh_extra_args:
            command.extend(['--ssh-extra-args', self.ssh_extra_args])

        if self.timeout:
            command.extend(['--timeout', self.timeout])

        if self.inventory:
            command.extend(['--inventory-file', self.inventory])

        if self.ssh_private_key:
            command.extend(['--private-key', self.ssh_private_key])

        if self.tags:
            command.extend(['--tags', self.tags])

        if self.skip_tags:
            command.extend(['--skip-tags', self.skip_tags])

        if self.extra_env_variables:
            if not isinstance(self.extra_env_variables, dict):
                msg = "extra_env_variables must be a dict"
                return actions.Result(error=msg)

        try:
            ansible_config_path = write_default_ansible_cfg(self.work_dir)
            env_variables = {
                'HOME': self.work_dir,
                'ANSIBLE_CONFIG': ansible_config_path
            }

            if self.extra_env_variables:
                env_variables.update(self.extra_env_variables)

            if self.use_openstack_credentials:
                env_variables.update({
                    'OS_AUTH_URL': context.auth_uri,
                    'OS_USERNAME': context.user_name,
                    'OS_AUTH_TOKEN': context.auth_token,
                    'OS_PROJECT_NAME': context.project_name})

            if self.queue_name:
                zaqar = self.get_messaging_client(context)
                queue = zaqar.queue(self.queue_name)
                # TODO(d0ugal): We don't have the log errors functionality
                # that processutils has, do we need to replicate that somehow?
                command = [str(c) for c in command]
                process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT,
                                           shell=False, bufsize=1,
                                           cwd=self.work_dir,
                                           env=env_variables)
                start = time.time()
                stdout = []
                lines = []
                for line in iter(process.stdout.readline, b''):
                    lines.append(line)
                    stdout.append(line)
                    if time.time() - start > 30:
                        queue.post(self.format_message(lines))
                        lines = []
                        start = time.time()
                queue.post(self.format_message(lines))
                process.stdout.close()
                returncode = process.wait()
                # TODO(d0ugal): This bit isn't ideal - as we redirect stderr to
                # stdout we don't know the difference. To keep the return dict
                # similar there is an empty stderr. We can use the return code
                # to determine if there was an error.
                if self.trash_output:
                    stdout = []
                    stderr = ""
                return {"stdout": "".join(stdout), "returncode": returncode,
                        "stderr": ""}

            stderr, stdout = processutils.execute(
                *command, cwd=self.work_dir,
                env_variables=env_variables,
                log_errors=processutils.LogErrors.ALL)
            return {"stderr": stderr, "stdout": stdout}
        finally:
            # NOTE(flaper87): clean the mess if debug is disabled.
            if not self.verbosity:
                shutil.rmtree(self.work_dir)
