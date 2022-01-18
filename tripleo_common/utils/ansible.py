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
from io import StringIO
import json
import logging
import multiprocessing
import os
from pathlib import Path
import shutil
import configparser
import tempfile
import yaml

from oslo_concurrency import processutils

from tripleo_common import constants

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
        '{}/library'.format(
            constants.DEFAULT_VALIDATIONS_BASEDIR))
    lookups_path = (
        '/root/.ansible/plugins/lookup:'
        '/usr/share/ansible/tripleo-plugins/lookup:'
        '/usr/share/ansible/plugins/lookup:'
        '{}/lookup_plugins'.format(
            constants.DEFAULT_VALIDATIONS_BASEDIR))
    callbacks_path = (
        '~/.ansible/plugins/callback:'
        '/usr/share/ansible/tripleo-plugins/callback:'
        '/usr/share/ansible/plugins/callback:'
        '{}/callback_plugins'.format(
            constants.DEFAULT_VALIDATIONS_BASEDIR))

    callbacks_whitelist = ','.join(['tripleo_dense', 'tripleo_profile_tasks',
                                    'tripleo_states'])
    action_plugins_path = (
        '~/.ansible/plugins/action:'
        '/usr/share/ansible/plugins/action:'
        '/usr/share/ansible/tripleo-plugins/action:'
        '{}/action_plugins'.format(
            constants.DEFAULT_VALIDATIONS_BASEDIR))
    filter_plugins_path = (
        '~/.ansible/plugins/filter:'
        '/usr/share/ansible/plugins/filter:'
        '/usr/share/ansible/tripleo-plugins/filter:'
        '{}/filter_plugins'.format(
            constants.DEFAULT_VALIDATIONS_BASEDIR))
    roles_path = ('{work_dir!s}/roles:'
                  '/root/.ansible/roles:'
                  '/usr/share/ansible/tripleo-roles:'
                  '/usr/share/ansible/roles:'
                  '/etc/ansible/roles:'
                  '{work_dir!s}'.format(work_dir=work_dir))

    config = configparser.ConfigParser()
    config.read(ansible_config_path)

    # NOTE(dvd): since ansible 2.12, we need to create the sections
    #            becase the base file is now empty.
    for section in ['defaults', 'ssh_connection']:
        if section not in config.sections():
            config.add_section(section)

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
    # unwanted accesse
    Path(log_path).touch()
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
    config.set('defaults', 'internal_poll_interval', '0.01')

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

    if override_ansible_cfg:
        sio_cfg = StringIO()
        sio_cfg.write(override_ansible_cfg)
        sio_cfg.seek(0)
        config.read_file(sio_cfg)
        sio_cfg.close()

    with open(ansible_config_path, 'w') as configfile:
        config.write(configfile)

    return ansible_config_path


def _get_inventory(inventory, work_dir):
    if not inventory:
        return None

    if (isinstance(inventory, str) and
            os.path.exists(inventory)):
        return inventory
    if not isinstance(inventory, str):
        inventory = yaml.safe_dump(inventory)

    path = os.path.join(work_dir, 'inventory.yaml')

    with open(path, 'w') as inv:
        inv.write(inventory)

    return path


def _get_ssh_private_key(ssh_private_key, work_dir):
    if not ssh_private_key:
        return None

    if (isinstance(ssh_private_key, str) and
            os.path.exists(ssh_private_key)):
        os.chmod(ssh_private_key, 0o600)
        return ssh_private_key

    path = os.path.join(work_dir, 'ssh_private_key')

    with open(path, 'w') as ssh_key:
        ssh_key.write(ssh_private_key)
    os.chmod(path, 0o600)

    return path


def _get_playbook(playbook, work_dir):
    if not playbook:
        return None

    if (isinstance(playbook, str) and
            os.path.exists(playbook)):
        return playbook
    if not isinstance(playbook, str):
        playbook = yaml.safe_dump(playbook)

    path = os.path.join(work_dir, 'playbook.yaml')

    with open(path, 'w') as pb:
        pb.write(playbook)

    return path


def run_ansible_playbook(playbook, work_dir=None, **kwargs):
    verbosity = kwargs.get('verbosity', 5)
    remove_work_dir = False
    if not work_dir:
        work_dir = tempfile.mkdtemp(prefix='tripleo-ansible')
        remove_work_dir = True

    playbook = _get_playbook(playbook, work_dir)
    ansible_playbook_cmd = "ansible-playbook"
    if 1 < verbosity < 6:
        verbosity_option = '-' + ('v' * (verbosity - 1))
        command = [ansible_playbook_cmd, verbosity_option,
                   playbook]
    else:
        command = [ansible_playbook_cmd, playbook]

    limit_hosts = kwargs.get('limit_hosts', None)
    if limit_hosts:
        command.extend(['--limit', limit_hosts])

    module_path = kwargs.get('module_path', None)
    if module_path:
        command.extend(['--module-path', module_path])

    become = kwargs.get('become', False)
    if become:
        command.extend(['--become'])

    become_user = kwargs.get('become_user', None)
    if become_user:
        command.extend(['--become-user', become_user])

    extra_vars = kwargs.get('extra_vars', None)
    if extra_vars:
        extra_vars = json.dumps(extra_vars)
        command.extend(['--extra-vars', extra_vars])

    flush_cache = kwargs.get('flush_cache', False)
    if flush_cache:
        command.extend(['--flush-cache'])

    forks = kwargs.get('forks', None)
    if forks:
        command.extend(['--forks', forks])

    ssh_common_args = kwargs.get('ssh_common_args', None)
    if ssh_common_args:
        command.extend(['--ssh-common-args', ssh_common_args])

    ssh_extra_args = kwargs.get('ssh_extra_args', None)
    if ssh_extra_args:
        command.extend(['--ssh-extra-args', ssh_extra_args])

    timeout = kwargs.get('timeout', None)
    if timeout:
        command.extend(['--timeout', timeout])

    inventory = _get_inventory(kwargs.get('inventory', None),
                               work_dir)
    if inventory:
        command.extend(['--inventory-file', inventory])

    tags = kwargs.get('tags', None)
    if tags:
        command.extend(['--tags', tags])

    skip_tags = kwargs.get('skip_tags', None)
    if skip_tags:
        command.extend(['--skip-tags', skip_tags])

    extra_env_variables = kwargs.get('extra_env_variables', None)
    override_ansible_cfg = kwargs.get('override_ansible_cfg', None)
    remote_user = kwargs.get('remote_user', None)
    ssh_private_key = kwargs.get('ssh_private_key', None)

    if extra_env_variables:
        if not isinstance(extra_env_variables, dict):
            msg = "extra_env_variables must be a dict"
            raise RuntimeError(msg)
        for key, value in extra_env_variables.items():
            extra_env_variables[key] = str(value)

    try:
        ansible_config_path = write_default_ansible_cfg(
            work_dir,
            remote_user,
            ssh_private_key=_get_ssh_private_key(
                ssh_private_key, work_dir),
            override_ansible_cfg=override_ansible_cfg)
        env_variables = {
            'HOME': work_dir,
            'ANSIBLE_LOCAL_TEMP': work_dir,
            'ANSIBLE_CONFIG': ansible_config_path,
        }

        profile_tasks = kwargs.get('profile_tasks', True)
        if profile_tasks:
            profile_tasks_limit = kwargs.get('profile_tasks_limit', 20)
            env_variables.update({
                # the whitelist could be collected from multiple
                # arguments if we find a use case for it
                'ANSIBLE_CALLBACKS_ENABLED':
                    'tripleo_dense,tripleo_profile_tasks,tripleo_states',
                'ANSIBLE_STDOUT_CALLBACK': 'tripleo_dense',
                'PROFILE_TASKS_TASK_OUTPUT_LIMIT':
                    str(profile_tasks_limit),
            })

        if extra_env_variables:
            env_variables.update(extra_env_variables)

        command = [str(c) for c in command]

        reproduce_command = kwargs.get('reproduce_command', None)
        command_timeout = kwargs.get('command_timeout', None)
        trash_output = kwargs.get('trash_output', None)
        if reproduce_command:
            command_path = os.path.join(work_dir,
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

        if command_timeout:
            command = ['timeout', '-s', 'KILL',
                       str(command_timeout)] + command

        LOG.info('Running ansible-playbook command: %s', command)

        stderr, stdout = processutils.execute(
            *command, cwd=work_dir,
            env_variables=env_variables,
            log_errors=processutils.LogErrors.ALL)
        if trash_output:
            stdout = ""
            stderr = ""
        return {"stderr": stderr, "stdout": stdout,
                "log_path": os.path.join(work_dir, 'ansible.log')}
    finally:
        try:
            if remove_work_dir:
                shutil.rmtree(work_dir)
        except Exception as e:
            msg = "An error happened while cleaning work directory: " + e
            raise RuntimeError(msg)
