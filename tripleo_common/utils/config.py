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
import logging
import os
import re
import six
import tempfile
import yaml


class Config(object):

    def __init__(self, orchestration_client):
        self.log = logging.getLogger(__name__ + ".Config")
        self.client = orchestration_client

    def get_role_data(self, stack):
        role_data = {}
        for output in stack.to_dict().get('outputs', {}):
            if output['output_key'] == 'RoleData':
                for role in output['output_value']:
                    role_data[role] = output['output_value'][role]
        return role_data

    def get_role_config(self, stack):
        role_data = {}
        for output in stack.to_dict().get('outputs', {}):
            if output['output_key'] == 'RoleConfig':
                for role in output['output_value']:
                    role_data[role] = output['output_value'][role]
        return role_data

    @staticmethod
    def _open_file(path):
        return os.fdopen(os.open(path,
                                 os.O_WRONLY | os.O_CREAT, 0o600),
                         'w')

    def _step_tags_to_when(self, sorted_tasks):
        for task in sorted_tasks:
            tag = task.get('tags', '')
            match = re.search('step([0-9]+)', tag)
            if match:
                step = match.group(1)
                whenexpr = task.get('when', None)
                if whenexpr is None:
                    task.update({"when": "step|int == %s" % step})
                else:
                    # Handle when: foo and a list of when conditionals
                    if not isinstance(whenexpr, list):
                        whenexpr = [whenexpr]
                    for w in whenexpr:
                        when_exists = re.search('step|int == [0-9]', "%s" % w)
                        if when_exists:
                            break
                    if when_exists:
                        # Skip to the next task,
                        # there is an existing 'step|int == N'
                        continue
                    whenexpr.insert(0, "step|int == %s" % step)
                    task['when'] = whenexpr

    def _write_playbook_get_tasks(self, tasks, role, filepath):
        playbook = []
        sorted_tasks = sorted(tasks, key=lambda x: x.get('tags', None))
        self._step_tags_to_when(sorted_tasks)
        playbook.append({'name': '%s playbook' % role,
                         'hosts': role,
                         'tasks': sorted_tasks})
        with self._open_file(filepath) as conf_file:
            yaml.safe_dump(playbook, conf_file, default_flow_style=False)
        return sorted_tasks

    def _mkdir(self, dirname):
        if not os.path.exists(dirname):
            try:
                os.mkdir(dirname, 0o700)
            except OSError as e:
                message = 'Failed to create: %s, error: %s' % (dirname,
                                                               str(e))
                raise OSError(message)

    def download_config(self, name, config_dir, config_type=None):
        # Get the stack object
        stack = self.client.stacks.get(name)
        # Create config directory
        self._mkdir(config_dir)
        tmp_path = tempfile.mkdtemp(prefix='tripleo-',
                                    suffix='-config',
                                    dir=config_dir)
        self.log.info("Generating configuration under the directory: "
                      "%s" % tmp_path)
        # Get role data:
        role_data = self.get_role_data(stack)
        for role_name, role in six.iteritems(role_data):
            role_path = os.path.join(tmp_path, role_name)
            self._mkdir(role_path)
            for config in config_type or role.keys():
                if config == 'step_config':
                    filepath = os.path.join(role_path, 'step_config.pp')
                    with self._open_file(filepath) as step_config:
                        step_config.write('\n'.join(step for step in
                                                    role[config]
                                                    if step is not None))
                else:
                    if 'upgrade_tasks' in config:
                        filepath = os.path.join(role_path, '%s_playbook.yaml' %
                                                config)
                        data = self._write_playbook_get_tasks(
                            role[config], role_name, filepath)
                    else:
                        try:
                            data = role[config]
                        except KeyError as e:
                            message = 'Invalid key: %s, error: %s' % (config,
                                                                      str(e))
                            raise KeyError(message)
                    filepath = os.path.join(role_path, '%s.yaml' % config)
                    with self._open_file(filepath) as conf_file:
                        yaml.safe_dump(data,
                                       conf_file,
                                       default_flow_style=False)
        role_config = self.get_role_config(stack)
        for config_name, config in six.iteritems(role_config):
            conf_path = os.path.join(tmp_path, config_name + ".yaml")
            with self._open_file(conf_path) as conf_file:
                conf_file.write(config)
        self.log.info("The TripleO configuration has been successfully "
                      "generated into: %s" % tmp_path)
        return tmp_path
