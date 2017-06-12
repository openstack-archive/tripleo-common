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
import six
import tempfile

import yaml

from mistral_lib import actions
from oslo_concurrency import processutils


def _write_data(data, suffix=''):
    temp_data = tempfile.NamedTemporaryFile(suffix=suffix)
    temp_data.write(data)
    temp_data.flush()
    return temp_data


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

    @property
    def inventory(self):
        if not self._inventory:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._inventory, six.string_types) and
                os.path.exists(self._inventory)):
            return open(self._inventory)
        else:
            self._inventory = yaml.safe_dump(self._inventory)

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the inventory generation failed
        return _write_data(self._inventory, suffix='.yaml')

    @property
    def ssh_private_key(self):
        if not self._ssh_private_key:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._ssh_private_key, six.string_types) and
                os.path.exists(self._ssh_private_key)):
            return open(self._ssh_private_key)

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the playbook generation failed
        return _write_data(self._ssh_private_key)

    def run(self, context):

        if 0 < self.verbosity < 6:
            verbosity_option = '-' + ('v' * self.verbosity)
            command = ['ansible', self.hosts, verbosity_option, ]
        else:
            command = ['ansible-playbook', self.hosts, ]

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

        inventory_file = self.inventory
        if inventory_file:
            command.extend(['--inventory-file', inventory_file.name])

        ssh_priv_key_file = self.ssh_private_key
        if ssh_priv_key_file:
            command.extend(['--private-key', ssh_priv_key_file.name])

        try:
            stderr, stdout = processutils.execute(
                *command, log_errors=processutils.LogErrors.ALL)
            return {"stderr": stderr, "stdout": stdout}
        finally:
            # NOTE(flaper87): Close the file
            # this is important as it'll also cleanup
            # temporary files
            if inventory_file:
                inventory_file.close()

            if ssh_priv_key_file:
                ssh_priv_key_file.close()


class AnsiblePlaybookAction(actions.Action):
    """Executes ansible playbook"""

    def __init__(self, **kwargs):
        self._kwargs_for_run = kwargs
        self._playbook = self._kwargs_for_run.pop('playbook', None)
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

    @property
    def inventory(self):
        if not self._inventory:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._inventory, six.string_types) and
                os.path.exists(self._inventory)):
            return open(self._inventory)
        else:
            self._inventory = yaml.safe_dump(self._inventory)

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the inventory generation failed
        return _write_data(self._inventory, suffix='.yaml')

    @property
    def playbook(self):
        if not self._playbook:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._playbook, six.string_types) and
                os.path.exists(self._playbook)):
            return open(self._playbook)
        else:
            self._playbook = yaml.safe_dump(self._playbook)

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the playbook generation failed
        return _write_data(self._playbook, suffix='.yaml')

    @property
    def ssh_private_key(self):
        if not self._ssh_private_key:
            return None

        # NOTE(flaper87): if it's a path, use it
        if (isinstance(self._ssh_private_key, six.string_types) and
                os.path.exists(self._ssh_private_key)):
            return open(self._ssh_private_key)

        # NOTE(flaper87):
        # We could probably catch parse errors here
        # but if we do, they won't be propagated and
        # we should not move forward with the action
        # if the playbook generation failed
        return _write_data(self._ssh_private_key)

    def run(self, context):
        playbook_file = self.playbook
        if 0 < self.verbosity < 6:
            verbosity_option = '-' + ('v' * self.verbosity)
            command = ['ansible-playbook', verbosity_option,
                       playbook_file.name]
        else:
            command = ['ansible-playbook', playbook_file.name]

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

        inventory_file = self.inventory
        if inventory_file:
            command.extend(['--inventory-file', inventory_file.name])

        ssh_priv_key_file = self.ssh_private_key
        if ssh_priv_key_file:
            command.extend(['--private-key', ssh_priv_key_file.name])

        try:
            stderr, stdout = processutils.execute(
                *command, log_errors=processutils.LogErrors.ALL)
            return {"stderr": stderr, "stdout": stdout}
        finally:
            # NOTE(flaper87): Close the file
            # this is important as it'll also cleanup
            # temporary files
            if inventory_file:
                inventory_file.close()

            if ssh_priv_key_file:
                ssh_priv_key_file.close()

            playbook_file.close()
