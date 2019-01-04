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
import warnings
import yaml

import jinja2

from tripleo_common import constants
from tripleo_common.utils.safe_import import git

warnings.filterwarnings('once')


class Config(object):

    def __init__(self, orchestration_client):
        self.log = logging.getLogger(__name__ + ".Config")
        self.client = orchestration_client
        self.stack_outputs = {}

    def get_server_names(self):
        servers = {}
        role_node_id_map = self.stack_outputs.get('ServerIdData', {})
        role_net_hostname_map = self.stack_outputs.get(
            'RoleNetHostnameMap', {})
        for role, hostnames in role_net_hostname_map.items():
            if hostnames:
                names = hostnames.get(constants.HOST_NETWORK) or []
                shortnames = [n.split(".%s." % constants.HOST_NETWORK)[0]
                              for n in names]
                for idx, name in enumerate(shortnames):
                    if 'server_ids' in role_node_id_map:
                        server_id = role_node_id_map['server_ids'][role][idx]
                        servers[server_id] = name.lower()
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

    def get_role_from_server_id(self, stack, server_id):
        server_id_data = self.stack_outputs.get('ServerIdData', {}
                                                ).get('server_ids', {})

        for k, v in server_id_data.items():
            if server_id in v:
                return k

    def get_deployment_resource_id(self, deployment):
        if '/' in deployment.attributes['value']['deployment']:
            deployment_stack_id = \
                deployment.attributes['value']['deployment'].split('/')[-1]
            deployment_resource_id = self.client.resources.get(
                deployment_stack_id,
                'TripleOSoftwareDeployment').physical_resource_id
        else:
            deployment_resource_id = \
                deployment.attributes['value']['deployment']
        return deployment_resource_id

    def get_config_dict(self, deployment_resource_id):
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

    def get_role_config(self):
        role_config = self.stack_outputs.get('RoleConfig', {})
        # RoleConfig can exist as a stack output but have a value of None
        return role_config or {}

    @staticmethod
    def _open_file(path):
        return os.fdopen(
            os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w')

    def _write_tasks_per_step(self, tasks, role, filepath, step):

        def step_in_task(task, step):
            whenexpr = task.get('when', None)
            if whenexpr is None:
                # If no step is defined, it will be executed for all
                # steps.
                return True
            if not isinstance(whenexpr, list):
                whenexpr = [whenexpr]
            for w in whenexpr:
                # make \|int optional incase forgotten; use only step digit:
                match = re.search('step(\|int)? == ([0-9]+)$', "%s" % w)
                if match:
                    if match.group(2) == str(step):
                        return True
                    else:
                        return False
            return True

        tasks_per_step = [task for task in tasks if step_in_task(task, step)]
        with self._open_file(filepath) as conf_file:
            yaml.safe_dump(tasks_per_step, conf_file, default_flow_style=False)
        return tasks_per_step

    def initialize_git_repo(self, dirname):
        repo = git.Repo.init(dirname)
        gitignore_path = os.path.join(dirname, '.gitignore')

        # Ignore tarballs, which we use for the export process
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w') as f:
                f.write('*.tar.gz\n')
            # For some reason using repo.index.add is not working, so go
            # directly to the GitCmd interface.
            repo.git.add('.gitignore')

        return repo

    def snapshot_config_dir(self, repo, commit_message):
        if repo.is_dirty(untracked_files=True):
            self.log.info('Snapshotting {}'.format(repo.working_dir))
            # Use repo.git.add directly as repo.index.add defaults to forcing
            # commit of ignored files, which we don't want.
            repo.git.add('.')
            commit = repo.index.commit(commit_message)
            self.log.info('Created commit {}'.format(commit.hexsha))
        else:
            self.log.info('No changes to commit')

    def _mkdir(self, dirname):
        if not os.path.exists(dirname):
            try:
                os.makedirs(dirname, 0o700)
            except OSError as e:
                message = 'Failed to create: %s, error: %s' % (dirname,
                                                               str(e))
                raise OSError(message)

    def create_config_dir(self, config_dir, preserve_config_dir=True):
        # Create config directory
        if os.path.exists(config_dir) and preserve_config_dir is False:
            try:
                self.log.info("Directory %s already exists, removing"
                              % config_dir)
                shutil.rmtree(config_dir)
            except OSError as e:
                message = 'Failed to remove: %s, error: %s' % (config_dir,
                                                               str(e))
                raise OSError(message)

    def fetch_config(self, name):
        # Get the stack object
        stack = self.client.stacks.get(name)
        self.stack_outputs = {i['output_key']: i['output_value']
                              for i in stack.outputs}
        return stack

    def validate_config(self, template_data, yaml_file):
        try:
            yaml.safe_load(template_data)
        except (yaml.scanner.ScannerError, yaml.YAMLError) as e:
            self.log.error("Config for file {} contains invalid yaml, got "
                           "error {}".format(yaml_file, e))
            raise e

    def write_config(self, stack, name, config_dir, config_type=None):
        # Get role data:
        role_data = self.stack_outputs.get('RoleData', {})
        role_group_vars = self.stack_outputs.get('RoleGroupVars', {})
        allnodes_vars = self.stack_outputs.get('AllNodesConfig', {})
        for role_name, role in six.iteritems(role_data):
            role_path = os.path.join(config_dir, role_name)
            self._mkdir(role_path)
            for config in config_type or role.keys():
                if config in constants.EXTERNAL_TASKS:
                    # external tasks are collected globally, not per-role
                    continue
                elif config == 'step_config':
                    filepath = os.path.join(role_path, 'step_config.pp')
                    with self._open_file(filepath) as step_config:
                        step_config.write(role[config])
                elif config == 'ansible_group_vars':
                    # NOTE(aschultz): ansible group vars are for specific role
                    # services so we merge them in with the others so they
                    # end up in the role vars. This means the last var
                    # definition wins and will override them all.
                    if role_name not in role_group_vars:
                        role_group_vars[role_name] = {}
                    role_group_vars[role_name].update(role[config])
                else:
                    # NOTE(jfrancoa): Move this upgrade_tasks condition to the
                    # upper level once THT is adapted. We include it here to
                    # allow the CI to pass until THT changed is not merged.
                    if config == 'upgrade_tasks':
                        for i in range(constants.UPGRADE_STEPS_MAX):
                            filepath = os.path.join(role_path, '%s_step%s.yaml'
                                                    % (config, i))
                            self._write_tasks_per_step(role[config], role_name,
                                                       filepath, i)
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

        role_config = self.get_role_config()
        for config_name, config in six.iteritems(role_config):
            conf_path = os.path.join(config_dir, config_name + ".yaml")
            with self._open_file(conf_path) as conf_file:
                if isinstance(config, list) or isinstance(config, dict):
                    yaml.safe_dump(config, conf_file, default_flow_style=False)
                else:
                    conf_file.write(config)

        # Get deployment data
        self.log.info("Getting deployment data from Heat...")
        deployments_data = self.get_deployment_data(name)

        # server_deployments is a dict of server name to a list of deployments
        # (dicts) associated with that server
        server_deployments = {}
        # server_names is a dict of server id to server_name for easier lookup
        server_names = self.get_server_names()
        server_ids = dict([(v, k) for (k, v) in server_names.items()])
        # server_deployment_names is a dict of server names to deployment names
        # for that role. The deployment names are further separated in their
        # own dict with keys of pre_deployment/post_deployment.
        server_deployment_names = {}
        # server_roles is a dict of server name to server role for easier
        # lookup
        server_roles = {}

        for deployment in deployments_data:
            # Check if the deployment value is the resource name. If that's the
            # case, Heat did not create a physical_resource_id for this
            # deployment since it does not trigger on this stack action. Such
            # as a deployment that only triggers on DELETE, but this is a stack
            # create. If that's the case, just skip this deployment, otherwise
            # it will result in a Not found error if we try and query the
            # deployment API for this deployment.
            dep_value_resource_name = deployment.attributes[
                'value'].get('deployment') == 'TripleOSoftwareDeployment'

            # if not check the physical_resource_id
            if not dep_value_resource_name:
                deployment_resource_id = self.get_deployment_resource_id(
                    deployment)

            if dep_value_resource_name or not deployment_resource_id:
                warnings.warn('Skipping deployment %s because it has no '
                              'valid uuid (physical_resource_id) '
                              'associated.' %
                              deployment.physical_resource_id)
                continue

            server_id = deployment.attributes['value']['server']
            config_dict = self.get_config_dict(deployment_resource_id)

            # deployment_name should be set via the name property on the
            # Deployment resources in the templates, however, if it's None
            # or empty string, default to the name of the parent_resource.
            deployment_name = deployment.attributes['value'].get(
                'name') or deployment.parent_resource
            if not deployment_name:
                message = "The deployment name cannot be determined. It " \
                          "should be set via the name property on the " \
                          "Deployment resources in the templates."
                raise ValueError(message)

            try:
                int(deployment_name)
            except ValueError:
                pass
            else:
                # We can't have an integer here, let's figure out the
                # grandparent resource name
                deployment_ref = deployment.attributes['value']['deployment']
                if '/' in deployment_ref:
                    deployment_stack_id = deployment_ref.split('/')[-1]
                else:
                    for link in deployment.links:
                        if link['rel'] == 'stack':
                            deployment_stack_id = link['href'].split('/')[-1]
                            break
                    else:
                        raise ValueError("Couldn't not find parent stack")
                deployment_stack = self.client.stacks.get(
                    deployment_stack_id, resolve_outputs=False)
                parent_stack = deployment_stack.parent
                resources = self.client.resources.list(
                    name,
                    nested_depth=constants.NESTED_DEPTH,
                    filters=dict(physical_resource_id=parent_stack))
                if not resources:
                    message = "The deployment resource grandparent name" \
                              "could not be determined."
                    raise ValueError(message)
                deployment_name = resources[0].resource_name
            config_dict['deployment_name'] = deployment_name

            # reset deploy_server_id to the actual server_id since we have to
            # use a dummy server resource to create the deployment in the
            # templates
            deploy_server_id_input = \
                [i for i in config_dict['inputs']
                 if i['name'] == 'deploy_server_id'].pop()
            deploy_server_id_input['value'] = server_id

            # We don't want to fail if server_id can't be found, as it's
            # most probably due to blacklisted nodes. However we fail for
            # other errors.
            try:
                server_deployments.setdefault(
                    server_names[server_id],
                    []).append(config_dict)
            except KeyError:
                self.log.warning('Server with id %s is ignored from config '
                                 '(may be blacklisted)' % server_id)
                # continue the loop as this server_id is probably excluded
                continue
            except Exception as err:
                err_msg = ('Error retrieving server name from this server_id: '
                           '%s with this error: %s' % server_id, err)
                raise Exception(err_msg)

            role = self.get_role_from_server_id(stack, server_id)
            server_pre_deployments = server_deployment_names.setdefault(
                server_names[server_id], {}).setdefault(
                'pre_deployments', [])
            server_post_deployments = server_deployment_names.setdefault(
                server_names[server_id], {}).setdefault(
                'post_deployments', [])

            server_roles[server_names[server_id]] = role

            # special handling of deployments that are run post the deploy
            # steps. We have to look these up based on the
            # physical_resource_id, but these names should be consistent since
            # they are consistent interfaces in our templates.
            if 'ExtraConfigPost' in deployment.physical_resource_id or \
                    'PostConfig' in deployment.physical_resource_id:
                if deployment_name not in server_post_deployments:
                    server_post_deployments.append(deployment_name)
            else:
                if deployment_name not in server_pre_deployments:
                    server_pre_deployments.append(deployment_name)

        env, templates_path = self.get_jinja_env(config_dir)

        templates_dest = os.path.join(config_dir, 'templates')
        self._mkdir(templates_dest)
        shutil.copyfile(os.path.join(templates_path, 'heat-config.j2'),
                        os.path.join(templates_dest, 'heat-config.j2'))

        group_vars_dir = os.path.join(config_dir, 'group_vars')
        self._mkdir(group_vars_dir)
        # Write allnodes_vars to 'overcloud' group as it doesn't apply
        # to the undercloud, and 'overcloud' is the inventory group
        # for all overcloud nodes, regardless of the --stack name.
        filepath = os.path.join(group_vars_dir, 'overcloud.yaml')
        with self._open_file(filepath) as vars_file:
            yaml.safe_dump(allnodes_vars, vars_file, default_flow_style=False)

        host_vars_dir = os.path.join(config_dir, 'host_vars')
        self._mkdir(host_vars_dir)

        for server, deployments in server_deployments.items():
            deployment_template = env.get_template('deployment.j2')

            for d in deployments:

                server_deployment_dir = os.path.join(
                    config_dir, server_roles[server], server)
                self._mkdir(server_deployment_dir)
                deployment_path = os.path.join(
                    server_deployment_dir, d['deployment_name'])

                # See if the config can be loaded as a JSON data structure
                # In some cases, it may already be JSON (hiera), or it may just
                # be a string (script). In those cases, just use the value
                # as-is.
                try:
                    data = json.loads(d['config'])
                except Exception:
                    data = d['config']

                # If the value is not a string already, pretty print it as a
                # string so it's rendered in a readable format.
                if not (isinstance(data, six.text_type) or
                        isinstance(data, six.string_types)):
                    data = json.dumps(data, indent=2)

                d['config'] = data

                # The hiera Heat hook expects an actual dict for the config
                # value, not a scalar. All other hooks expect a scalar.
                if d['group'] == 'hiera':
                    d['scalar'] = False
                else:
                    d['scalar'] = True

                if d['group'] == 'os-apply-config':
                    message = ("group:os-apply-config is deprecated. "
                               "Deployment %s will not be applied by "
                               "config-download." % d['deployment_name'])
                    warnings.warn(message, DeprecationWarning)

                with open(deployment_path, 'wb') as f:
                    template_data = deployment_template.render(
                        deployment=d,
                        server_id=server_ids[server])
                    self.validate_config(template_data, deployment_path)
                    f.write(template_data.encode('utf-8'))

        # Render group_vars
        for role in set(server_roles.values()):
            group_var_role_path = os.path.join(group_vars_dir, role)
            # NOTE(aschultz): we just use yaml.safe_dump for the vars because
            # the vars should already bein a hash for for ansible.
            # See LP#1801162 for previous issues around using jinja for this
            with open(group_var_role_path, 'w') as group_vars_file:
                yaml.safe_dump(role_group_vars[role], group_vars_file,
                               default_flow_style=False)

        # Render host_vars
        for server, deployments in server_deployment_names.items():
            host_var_server_path = os.path.join(host_vars_dir, server)
            host_var_server_template = env.get_template('host_var_server.j2')

            with open(host_var_server_path, 'w') as f:
                template_data = host_var_server_template.render(
                    role=server_roles[server],
                    pre_deployments=deployments['pre_deployments'],
                    post_deployments=deployments['post_deployments'])
                self.validate_config(template_data, host_var_server_path)
                f.write(template_data)

        shutil.copyfile(
            os.path.join(templates_path, 'deployments.yaml'),
            os.path.join(config_dir, 'deployments.yaml'))

        self.log.info("The TripleO configuration has been successfully "
                      "generated into: %s" % config_dir)
        return config_dir

    def download_config(self, name, config_dir, config_type=None,
                        preserve_config_dir=True, commit_message=None):

        if commit_message is None:
            commit_message = 'Automatic commit of config-download'

        # One step does it all
        stack = self.fetch_config(name)
        self.create_config_dir(config_dir, preserve_config_dir)
        self._mkdir(config_dir)
        git_repo = self.initialize_git_repo(config_dir)
        self.log.info("Generating configuration under the directory: "
                      "%s" % config_dir)
        self.write_config(stack, name, config_dir, config_type)
        self.snapshot_config_dir(git_repo, commit_message)
        return config_dir
