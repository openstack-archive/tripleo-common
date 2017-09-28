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
import logging
import os
import re
import shutil
import six
import tempfile
import yaml

import jinja2

from tripleo_common import constants


class Config(object):

    def __init__(self, orchestration_client):
        self.log = logging.getLogger(__name__ + ".Config")
        self.client = orchestration_client
        self.__server_id_data = None

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

    def get_server_data(self, stack, role_names,
                        nested_depth=constants.NESTED_DEPTH):
        servers = []
        server_resource_types = [constants.SERVER_RESOURCE_TYPES % r
                                 for r in role_names]

        for server_resource_type in server_resource_types:
            servers += self.client.resources.list(
                stack,
                nested_depth=nested_depth,
                filters=dict(type=server_resource_type),
                with_detail=True)
        return servers

    def get_deployment_data(self, stack,
                            nested_depth=constants.NESTED_DEPTH):
        deployments = self.client.resources.list(
            stack,
            nested_depth=nested_depth,
            filters=dict(name=constants.TRIPLEO_DEPLOYMENT_RESOURCE),
            with_detail=True)
        # Sort by creation time
        deployments = sorted(deployments, key=lambda d: d.creation_time)
        return deployments

    def get_server_id_data(self, stack):
        for output in stack.to_dict().get('outputs', {}):
            if output['output_key'] == 'ServerIdData':
                return output['output_value']['server_ids']

    def get_role_from_server_id(self, stack, server_id):
        if self.__server_id_data is None:
            self.__server_id_data = self.get_server_id_data(stack)

        for k, v in self.__server_id_data.items():
            if server_id in v:
                return k

    def get_config_dict(self, deployment):
        if '/' in deployment.attributes['value']['deployment']:
            deployment_stack_id = \
                deployment.attributes['value']['deployment'].split('/')[-1]
            deployment_resource_id = self.client.resources.get(
                deployment_stack_id,
                'TripleOSoftwareDeployment').physical_resource_id
        else:
            deployment_resource_id = \
                deployment.attributes['value']['deployment']
        deployment_rsrc = self.client.software_deployments.get(
            deployment_resource_id)
        config = self.client.software_configs.get(
            deployment_rsrc.config_id)

        return config.to_dict()

    def get_jinja_env(self, tmp_path):
        templates_path = os.path.join(
            os.path.dirname(__file__), '..', 'templates')
        self._mkdir(os.path.join(tmp_path, 'templates'))
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(templates_path))
        env.trim_blocks = True
        return env, templates_path

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
                if whenexpr:
                    # Handle when: foo and a list of when conditionals
                    if not isinstance(whenexpr, list):
                        whenexpr = [whenexpr]
                    for w in whenexpr:
                        when_exists = re.search('step|int == [0-9]', w)
                        if when_exists:
                            break
                    if when_exists:
                        # Skip to the next task,
                        # there is an existing 'step|int == N'
                        continue
                    whenexpr.append("step|int == %s" % step)
                    task['when'] = whenexpr
                else:
                    task.update({"when": "step|int == %s" % step})

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

        # Get deployment data
        self.log.info("Getting server data from Heat...")
        server_data = self.get_server_data(name, role_data.keys())
        self.log.info("Getting deployment data from Heat...")
        deployments_data = self.get_deployment_data(name)

        # server_deployments is a dict of server name to a list of deployments
        # (dicts) associated with that server
        server_deployments = {}
        # server_ids is a dict of server_name to server_id for easier lookup
        server_ids = {}
        # role_deployment_names is a dict of role names to deployment names for
        # that role. The deployment names are futher separated in their own
        # dict with keys of pre_deployment/post_deployment.
        role_deployment_names = {}

        for deployment in deployments_data:
            server_id = deployment.attributes['value']['server']
            server = [s for s in server_data
                      if s.physical_resource_id == server_id or
                      s.attributes.get('OS::stack_id') == server_id].pop()
            server_ids.setdefault(server.attributes['name'], server_id)
            config_dict = self.get_config_dict(deployment)

            # deployment_name should be set via the name property on the
            # Deployment resources in the templates, however, if it's None,
            # default to the name of the parent_resource
            deployment_name = deployment.attributes['value'].get(
                'name', deployment.parent_resource)
            config_dict['deployment_name'] = deployment_name

            # reset deploy_server_id to the actual server_id since we have to
            # use a dummy server resource to create the deployment in the
            # templates
            deploy_server_id_input = \
                [i for i in config_dict['inputs']
                 if i['name'] == 'deploy_server_id'].pop()
            deploy_server_id_input['value'] = server_id

            server_deployments.setdefault(
                server.attributes['name'],
                []).append(config_dict)

            role = self.get_role_from_server_id(stack, server_id)
            role_deployments = role_deployment_names.setdefault(role, {})
            role_pre_deployments = role_deployments.setdefault(
                'pre_deployments', [])
            role_post_deployments = role_deployments.setdefault(
                'post_deployments', [])

            # special handling of deployments that are run post the deploy
            # steps. We have to look these up based on the
            # physical_resource_id, but these names should be consistent since
            # they are consistent interfaces in our templates.
            if 'ExtraConfigPost' in deployment.physical_resource_id or \
                    'PostConfig' in deployment.physical_resource_id:
                if deployment_name not in role_post_deployments:
                    role_post_deployments.append(deployment_name)
            else:
                if deployment_name not in role_pre_deployments:
                    role_pre_deployments.append(deployment_name)

        env, templates_path = self.get_jinja_env(tmp_path)

        templates_dest = os.path.join(tmp_path, 'templates')
        self._mkdir(templates_dest)
        shutil.copyfile(os.path.join(templates_path, 'heat-config.j2'),
                        os.path.join(templates_dest, 'heat-config.j2'))

        group_vars_dir = os.path.join(tmp_path, 'group_vars')
        self._mkdir(group_vars_dir)

        for server, deployments in server_deployments.items():
            group_var_server_path = os.path.join(group_vars_dir, server)
            group_var_server_template = env.get_template('group_var_server.j2')

            for d in deployments:
                if isinstance(d['config'], dict):
                    d['config'] = json.dumps(d['config'])
                if d['group'] == 'hiera':
                    d['scalar'] = False
                else:
                    d['scalar'] = True

            with open(group_var_server_path, 'w') as f:
                f.write(group_var_server_template.render(
                    deployments=deployments,
                    server_id=server_ids[server]))

        for role, deployments in role_deployment_names.items():
            group_var_role_path = os.path.join(group_vars_dir, role)
            group_var_role_template = env.get_template('group_var_role.j2')

            with open(group_var_role_path, 'w') as f:
                f.write(group_var_role_template.render(
                    role=role,
                    pre_deployments=deployments['pre_deployments'],
                    post_deployments=deployments['post_deployments']))

        for role_name, role in six.iteritems(role_data):
            role_path = os.path.join(tmp_path, role_name)

            shutil.copyfile(
                os.path.join(templates_path, 'deployments.yaml'),
                os.path.join(role_path, 'deployments.yaml'))

        self.log.info("The TripleO configuration has been successfully "
                      "generated into: %s" % tmp_path)
        return tmp_path
