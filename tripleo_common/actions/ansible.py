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
from datetime import datetime
import json
import logging
import multiprocessing
import os
import shutil
import six
from six.moves import configparser
from six.moves import cStringIO as StringIO
import sys
import tempfile
import time
import yaml

from mistral_lib import actions
from oslo_concurrency import processutils
from oslo_rootwrap import subprocess

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common import inventory

LOG = logging.getLogger(__name__)


def write_default_ansible_cfg(work_dir,
                              remote_user,
                              ssh_private_key=None,
                              transport=None,
                              base_ansible_cfg='/etc/ansible/ansible.cfg',
                              override_ansible_cfg=None):
    ansible_config_path = os.path.join(work_dir, 'ansible.cfg')
    shutil.copy(base_ansible_cfg, ansible_config_path)

    modules_path = (
        '/root/.ansible/plugins/modules:'
        '/usr/share/ansible/tripleo-plugins/modules:'
        '/usr/share/ansible/plugins/modules:'
        '/usr/share/ansible-modules:'
        '{}/library:'
        '{}/library'.format(constants.DEFAULT_VALIDATIONS_BASEDIR,
                            constants.DEFAULT_VALIDATIONS_LEGACY_BASEDIR))
    lookups_path = (
        '/root/.ansible/plugins/lookup:'
        '/usr/share/ansible/tripleo-plugins/lookup:'
        '/usr/share/ansible/plugins/lookup:'
        '{}/lookup_plugins:'
        '{}/lookup_plugins'.format(
            constants.DEFAULT_VALIDATIONS_BASEDIR,
            constants.DEFAULT_VALIDATIONS_LEGACY_BASEDIR))
    callbacks_path = (
        '~/.ansible/plugins/callback:'
        '/usr/share/ansible/tripleo-plugins/callback:'
        '/usr/share/ansible/plugins/callback:'
        '{}/callback_plugins:'
        '{}/callback_plugins'.format(
            constants.DEFAULT_VALIDATIONS_BASEDIR,
            constants.DEFAULT_VALIDATIONS_LEGACY_BASEDIR))

    callbacks_whitelist = ','.join(['tripleo_dense', 'tripleo_profile_tasks',
                                    'tripleo_states'])
    action_plugins_path = (
        '~/.ansible/plugins/action:'
        '/usr/share/ansible/plugins/action:'
        '/usr/share/ansible/tripleo-plugins/action:'
        '{}/action_plugins:'
        '{}/action_plugins'.format(
            constants.DEFAULT_VALIDATIONS_BASEDIR,
            constants.DEFAULT_VALIDATIONS_LEGACY_BASEDIR))
    filter_plugins_path = (
        '~/.ansible/plugins/filter:'
        '/usr/share/ansible/plugins/filter:'
        '/usr/share/ansible/tripleo-plugins/filter:'
        '{}/filter_plugins:'
        '{}/filter_plugins'.format(
            constants.DEFAULT_VALIDATIONS_BASEDIR,
            constants.DEFAULT_VALIDATIONS_LEGACY_BASEDIR))
    roles_path = ('%(work_dir)s/roles:'
                  '/root/.ansible/roles:'
                  '/usr/share/ansible/tripleo-roles:'
                  '/usr/share/ansible/roles:'
                  '/etc/ansible/roles:'
                  '%(ooo_val_path)s/roles:'
                  '%(work_dir)s' % {
                      'work_dir': work_dir,
                      'ooo_val_path':
                          constants.DEFAULT_VALIDATIONS_LEGACY_BASEDIR
                  })

    config = configparser.ConfigParser()
    config.read(ansible_config_path)

    config.set('defaults', 'retry_files_enabled', 'False')
    config.set('defaults', 'roles_path', roles_path)
    config.set('defaults', 'library', modules_path)
    config.set('defaults', 'callback_plugins', callbacks_path)
    config.set('defaults', 'callback_whitelist', callbacks_whitelist)
    config.set('defaults', 'stdout_callback', 'tripleo_dense')
    config.set('defaults', 'action_plugins', action_plugins_path)
    config.set('defaults', 'lookup_plugins', lookups_path)
    config.set('defaults', 'filter_plugins', filter_plugins_path)

    log_path = os.path.join(work_dir, 'ansible.log')
    config.set('defaults', 'log_path', log_path)
    if os.path.exists(log_path):
        new_path = (log_path + '-' +
                    datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        os.rename(log_path, new_path)

    # Create the log file, and set some rights on it in order to prevent
    # unwanted access
    open(log_path, 'a').close()
    os.chmod(log_path, 0o640)

    config.set('defaults', 'forks', str(min(
        multiprocessing.cpu_count() * 4, 100)))
    config.set('defaults', 'timeout', '30')
    config.set('defaults', 'gather_timeout', '30')

    # Setup fact cache to improve playbook execution speed
    config.set('defaults', 'gathering', 'smart')
    config.set('defaults', 'fact_caching', 'jsonfile')
    config.set('defaults', 'fact_caching_connection',
               '~/.ansible/fact_cache')
    # NOTE(mwhahaha): only gather the bare minimum facts because this has
    # direct impact on how fast ansible can go.
    config.set('defaults', 'gather_subset', '!all,min')
    # NOTE(mwhahaha): this significantly affects performation per ansible#73654
    config.set('defaults', 'inject_facts_as_vars', 'false')

    # Set the pull interval to lower CPU overhead
    config.set('defaults', 'internal_poll_interval', '0.05')

    # Set the interpreter discovery to auto mode.
    config.set('defaults', 'interpreter_python', 'auto')

    # Expire facts in the fact cache after 7200s (2h)
    config.set('defaults', 'fact_caching_timeout', '7200')

    # mistral user has no home dir set, so no place to save a known hosts file
    config.set('ssh_connection', 'ssh_args',
               '-o UserKnownHostsFile=/dev/null '
               '-o StrictHostKeyChecking=no '
               '-o ControlMaster=auto '
               '-o ControlPersist=30m '
               '-o ServerAliveInterval=5 '
               '-o ServerAliveCountMax=5 '
               '-o PreferredAuthentications=publickey')
    config.set('ssh_connection', 'control_path_dir',
               os.path.join(work_dir, 'ansible-ssh'))
    config.set('ssh_connection', 'retries', '8')
    config.set('ssh_connection', 'pipelining', 'True')
    # Related to https://github.com/ansible/ansible/issues/22127
    config.set('ssh_connection', 'scp_if_ssh', 'True')

    # Set connection info in config file so that subsequent/nested ansible
    # calls can re-use it
    if remote_user:
        config.set('defaults', 'remote_user', remote_user)
    if ssh_private_key:
        config.set('defaults', 'private_key_file', ssh_private_key)
    if transport:
        config.set('defaults', 'transport', transport)

    if override_ansible_cfg:
        sio_cfg = StringIO()
        sio_cfg.write(override_ansible_cfg)
        sio_cfg.seek(0)
        config.read_file(sio_cfg)
        sio_cfg.close()

    with open(ansible_config_path, 'w') as configfile:
        config.write(configfile)

    return ansible_config_path


class AnsiblePlaybookAction(base.TripleOAction):
    """Executes ansible playbook"""

    def __init__(self, **kwargs):
        self._kwargs_for_run = kwargs
        self._playbook = self._kwargs_for_run.pop('playbook', None)
        self.playbook_name = self._kwargs_for_run.pop('playbook_name',
                                                      'playbook.yaml')
        self.plan_name = self._kwargs_for_run.pop('plan_name', None)
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
        self.config_download_args = self._kwargs_for_run.pop(
            'config_download_args', None)
        self.extra_env_variables = self._kwargs_for_run.pop(
            'extra_env_variables', None)
        self.queue_name = self._kwargs_for_run.pop('queue_name', None)
        self.reproduce_command = self._kwargs_for_run.pop(
            'reproduce_command', True)
        self.execution_id = self._kwargs_for_run.pop('execution_id', None)
        self._work_dir = self._kwargs_for_run.pop(
            'work_dir', None)
        self.max_message_size = self._kwargs_for_run.pop(
            'max_message_size', 1048576)
        self.gather_facts = self._kwargs_for_run.pop('gather_facts', False)
        self.trash_output = self._kwargs_for_run.pop('trash_output', False)
        self.profile_tasks = self._kwargs_for_run.pop('profile_tasks', True)
        self.profile_tasks_limit = self._kwargs_for_run.pop(
            'profile_tasks_limit', 20)
        self.blacklisted_hostnames = self._kwargs_for_run.pop(
            'blacklisted_hostnames', [])
        self.override_ansible_cfg = self._kwargs_for_run.pop(
            'override_ansible_cfg', None)
        self.command_timeout = self._kwargs_for_run.pop(
            'command_timeout', None)

        self._remove_work_dir = False

    @property
    def work_dir(self):
        if self._work_dir:
            return self._work_dir
        self._work_dir = tempfile.mkdtemp(prefix='ansible-mistral-action')
        self._remove_work_dir = True
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

        path = os.path.join(self.work_dir, self.playbook_name)

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
            os.chmod(self._ssh_private_key, 0o600)
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

    def format_message(self, message):
        type_ = 'tripleo.ansible-playbook.{}'.format(self.playbook_name)
        return {
            'body': {
                'type': type_,
                'payload': {
                    'message': message,
                    'plan_name': self.plan_name,
                    'status': 'RUNNING',
                    'execution': {'id': self.execution_id}}}}

    def post_message(self, queue, message):
        """Posts message to queue

        Breaks the message up by maximum message size if needed.
        """

        start = 0
        # We use 50% of the max message size to account for any overhead
        # due to JSON encoding plus the wrapped dict structure from
        # format_message.
        message_size = int(self.max_message_size * 0.5)
        while True:
            end = start + message_size
            message_part = message[start:end]
            start = end
            if not message_part:
                return
            queue.post(self.format_message(message_part))

    def run(self, context):

        python_version = sys.version_info.major
        ansible_playbook_cmd = "ansible-playbook-{}".format(python_version)

        if 1 < self.verbosity < 6:
            verbosity_option = '-' + ('v' * (self.verbosity - 1))
            command = [ansible_playbook_cmd, verbosity_option,
                       self.playbook]
        else:
            command = [ansible_playbook_cmd, self.playbook]

        # --limit should always take precedence over blacklisted hosts.
        # https://bugzilla.redhat.com/show_bug.cgi?id=1857298
        if self.limit_hosts:
            command.extend(['--limit', self.limit_hosts])
        elif self.blacklisted_hostnames:
            host_pattern = ':'.join(
                ['!%s' % h for h in self.blacklisted_hostnames if h])
            command.extend(['--limit', host_pattern])

        if self.module_path:
            command.extend(['--module-path', self.module_path])

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

        if self.tags:
            command.extend(['--tags', self.tags])

        if self.skip_tags:
            command.extend(['--skip-tags', self.skip_tags])

        if self.config_download_args:
            command.extend(self.config_download_args)

        if self.extra_env_variables:
            if not isinstance(self.extra_env_variables, dict):
                msg = "extra_env_variables must be a dict"
                return actions.Result(error=msg)
            else:
                for key, value in self.extra_env_variables.items():
                    self.extra_env_variables[key] = six.text_type(value)

        if self.gather_facts:
            command.extend(['--gather-facts', self.gather_facts])

        try:
            ansible_config_path = write_default_ansible_cfg(
                self.work_dir,
                self.remote_user,
                ssh_private_key=self.ssh_private_key,
                override_ansible_cfg=self.override_ansible_cfg)
            env_variables = {
                'HOME': self.work_dir,
                'ANSIBLE_LOCAL_TEMP': self.work_dir,
                'ANSIBLE_CONFIG': ansible_config_path,
            }

            if self.profile_tasks:
                env_variables.update({
                    # the whitelist could be collected from multiple
                    # arguments if we find a use case for it
                    'ANSIBLE_CALLBACK_WHITELIST':
                        'tripleo_dense,tripleo_profile_tasks,tripleo_states',
                    'ANSIBLE_STDOUT_CALLBACK': 'tripleo_dense',
                    'PROFILE_TASKS_TASK_OUTPUT_LIMIT':
                        six.text_type(self.profile_tasks_limit),
                })

            if self.extra_env_variables:
                env_variables.update(self.extra_env_variables)

            if self.use_openstack_credentials:
                security_ctx = context.security
                env_variables.update({
                    'OS_AUTH_URL': security_ctx.auth_uri,
                    'OS_USERNAME': security_ctx.user_name,
                    'OS_AUTH_TOKEN': security_ctx.auth_token,
                    'OS_PROJECT_NAME': security_ctx.project_name})

            command = [str(c) for c in command]

            if self.reproduce_command:
                command_path = os.path.join(self.work_dir,
                                            "ansible-playbook-command.sh")
                with open(command_path, 'w') as f:
                    f.write('#!/bin/bash\n')
                    f.write('\n')
                    for var in env_variables:
                        f.write('%s="%s"\n' % (var, env_variables[var]))
                    f.write('\n')
                    f.write(' '.join(command))
                    f.write(' "$@"')
                    f.write('\n')

                os.chmod(command_path, 0o750)

            if self.command_timeout:
                command = ['timeout', '-s', 'KILL',
                           str(self.command_timeout)] + command

            if self.queue_name:
                zaqar = self.get_messaging_client(context)
                queue = zaqar.queue(self.queue_name)
                # TODO(d0ugal): We don't have the log errors functionality
                # that processutils has, do we need to replicate that somehow?
                process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT,
                                           shell=False, bufsize=1,
                                           cwd=self.work_dir,
                                           env=env_variables,
                                           universal_newlines=True)
                start = time.time()
                stdout = []
                lines = []
                for line in iter(process.stdout.readline, ''):
                    lines.append(line)
                    if not self.trash_output:
                        stdout.append(line)
                    if time.time() - start > 30:
                        self.post_message(queue, ''.join(lines))
                        lines = []
                        start = time.time()
                self.post_message(queue, ''.join(lines))
                process.stdout.close()
                returncode = process.wait()
                # TODO(d0ugal): This bit isn't ideal - as we redirect stderr to
                # stdout we don't know the difference. To keep the return dict
                # similar there is an empty stderr. We can use the return code
                # to determine if there was an error.
                return {"stdout": "".join(stdout), "returncode": returncode,
                        "stderr": ""}

            LOG.info('Running ansible-playbook command: %s', command)

            stderr, stdout = processutils.execute(
                *command, cwd=self.work_dir,
                env_variables=env_variables,
                log_errors=processutils.LogErrors.ALL)
            if self.trash_output:
                stdout = ""
                stderr = ""
            return {"stderr": stderr, "stdout": stdout,
                    "log_path": os.path.join(self.work_dir, 'ansible.log')}
        finally:
            # NOTE(flaper87): clean the mess if debug is disabled.
            try:
                if not self.verbosity and self._remove_work_dir:
                    shutil.rmtree(self.work_dir)
            except Exception as e:
                msg = "An error happened while cleaning work directory: " + e
                LOG.error(msg)
                return actions.Result(error=msg)


class AnsibleGenerateInventoryAction(base.TripleOAction):
    """Executes tripleo-ansible-inventory to generate an inventory"""

    def __init__(self, **kwargs):
        self._kwargs_for_run = kwargs
        self.ansible_ssh_user = self._kwargs_for_run.pop(
            'ansible_ssh_user', 'tripleo-admin')
        self.undercloud_key_file = self._kwargs_for_run.pop(
            'undercloud_key_file', None)
        self.ansible_python_interpreter = self._kwargs_for_run.pop(
            'ansible_python_interpreter', None)
        self.work_dir = self._kwargs_for_run.pop(
            'work_dir', None)
        self.plan_name = self._kwargs_for_run.pop(
            'plan_name', 'overcloud')
        self.ssh_network = self._kwargs_for_run.pop(
            'ssh_network', 'ctlplane')

    def run(self, context):
        return inventory.generate_tripleo_ansible_inventory(
            heat=self.get_orchestration_client(context),
            work_dir=self.work_dir,
            plan=self.plan_name,
            auth=context.security,
            ansible_ssh_user=self.ansible_ssh_user,
            undercloud_key_file=self.undercloud_key_file,
            ansible_python_interpreter=self.ansible_python_interpreter,
            ssh_network=self.ssh_network)
