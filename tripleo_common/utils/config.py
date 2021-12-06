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

import git
import json
import logging
import os
import re
import shutil
import tempfile
import warnings
import yaml

import jinja2

from tripleo_common import constants
from tripleo_common import inventory

LOG = logging.getLogger(__name__)

warnings.filterwarnings('once', category=DeprecationWarning)
warnings.filterwarnings('once', category=UserWarning)


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
                        if server_id is not None:
                            servers[server_id] = name.lower()
        return servers

    def get_role_network_config_data(self):
        return self.stack_outputs.get("RoleNetworkConfigMap")

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

    def _write_tasks_per_step(self, tasks, filepath, step, strict=False):

        def step_in_task(task, step, strict):
            whenexpr = task.get('when', None)
            if whenexpr is None:
                if not strict:
                    # If no step is defined, it will be executed for all
                    # steps if strict is false
                    return True
                # We only want the task with the step defined.
                return False
            if not isinstance(whenexpr, list):
                whenexpr = [whenexpr]

            # Filter out boolean value and remove blanks
            flatten_when = "".join([re.sub(r'\s+', '', x)
                                    for x in whenexpr
                                    if isinstance(x, str)])
            # make \|int optional incase forgotten; use only step digit:
            # ()'s around step|int are also optional
            steps_found = re.findall(r'\(?step(?:\|int)?\)?==(\d+)',
                                     flatten_when)
            if steps_found:
                if str(step) in steps_found:
                    return True
                return False

            # No step found
            if strict:
                return False
            return True

        tasks_per_step = [task for task in tasks if step_in_task(task,
                                                                 step,
                                                                 strict)]
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
            self.log.info('Snapshotting %s', repo.working_dir)
            # Use repo.git.add directly as repo.index.add defaults to forcing
            # commit of ignored files, which we don't want.
            repo.git.add('.')
            commit = repo.index.commit(commit_message)
            self.log.info('Created commit %s', commit.hexsha)
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
                self.log.info("Directory %s already exists, removing",
                              config_dir)
                shutil.rmtree(config_dir)
            except OSError as e:
                message = 'Failed to remove: %s, error: %s' % (config_dir,
                                                               str(e))
                raise OSError(message)

        os.makedirs(config_dir, mode=0o700, exist_ok=True)

        # Create Runner friendly directory structure
        # https://ansible-runner.readthedocs.io/en/stable/intro.html#runner-artifacts-directory-hierarchy
        structure = [
            'artifacts',
            'env',
            'inventory',
            'profiling_data',
            'project',
            'roles',
        ]
        for d in structure:
            os.makedirs(os.path.join(config_dir, d), mode=0o700,
                        exist_ok=True)

        os.makedirs(os.path.join(config_dir, 'task_core'), mode=0o700,
                    exist_ok=True)

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
            self.log.error("Config for file %s contains invalid yaml, got "
                           "error %s", yaml_file, e)
            raise e

    def render_network_config(self, config_dir):
        role_network_config = self.get_role_network_config_data()
        if role_network_config is None:
            raise ValueError(
                'Old network config templates are possibly used, '
                'Please convert them before proceeding.')

        for role, config in role_network_config.items():
            config_path = os.path.join(config_dir, role, "NetworkConfig")
            # check if it's actual config or heat config_id
            # this will be dropped once we stop using SoftwareConfig
            if config is None:
                continue

            if isinstance(config, dict):
                str_config = json.dumps(config)
            else:
                str_config = self.client.software_configs.get(config).config
            if str_config:
                with self._open_file(config_path) as f:
                    f.write(str_config)

    def render_task_core(self, name, config_dir, role_data, server_roles,
                         role_group_vars, role_config):
        task_core_data = role_config.get('task_core_data', {})

        # create task core data directories
        task_core_dir = os.path.join(config_dir, 'task_core')
        self._mkdir(task_core_dir)

        task_core_services = []
        task_core_service_path = os.path.join(task_core_dir, 'services')
        self._mkdir(task_core_service_path)

        task_core_roles_path = os.path.join(task_core_dir, 'roles')
        self._mkdir(task_core_roles_path)

        # Render task-core deployment services from RoleConfig
        deploy_svcs = task_core_data.get('deployment_services', {})
        for svc, svc_data in deploy_svcs.items():
            svc_path = os.path.join(task_core_service_path, f"{svc}.yaml")
            with self._open_file(svc_path) as svc_file:
                if isinstance(svc_data, dict):
                    yaml.safe_dump(svc_data, svc_file,
                                   default_flow_style=False)
                else:
                    svc_file.write(svc_data)

        # Render task core services from roles
        for role_name, role in role_data.items():
            for svc, svc_data in role.get('core_services', {}).items():
                # add service name for filtering the roles later to aide in
                # migration
                task_core_services.append(svc)
                svc_path = os.path.join(task_core_service_path, f"{svc}.yaml")
                if os.path.exists(svc_path):
                    # already processed, just skip
                    continue
                svc_data.update({'id': svc, 'type': 'service'})
                with self._open_file(svc_path) as svc_file:
                    yaml.safe_dump(svc_data, svc_file,
                                   default_flow_style=False)

        # Render task-core role for deployer from RoleConfig
        task_core_deployer_role_file = os.path.join(task_core_roles_path,
                                                    "deployer.yaml")
        with self._open_file(task_core_deployer_role_file) as roles_file:
            deployment_roles = task_core_data.get('deployment_roles', {})
            yaml.safe_dump(deployment_roles, roles_file,
                           default_flow_style=False)

        # Render task-core roles file from RoleGroupVars, always include
        # deployment roles in overcloud role
        task_core_roles = deployment_roles
        for role in set(server_roles.values()):
            # RoleGroupVars has [role]ConfigData merged into it which
            # contains the enabled services for a role. Only add the services
            # that have core_services definitions
            enabled_svcs = role_group_vars[role].get('service_names', [])
            task_core_roles[role.lower()] = {
                'services': [svc for svc in enabled_svcs
                             if svc in task_core_services]
            }
        task_core_overcloud_role_file = os.path.join(task_core_roles_path,
                                                     f"{name}.yaml")
        with self._open_file(task_core_overcloud_role_file) as roles_file:
            yaml.safe_dump(task_core_roles, roles_file,
                           default_flow_style=False)

        task_core_inv_file = os.path.join(task_core_dir,
                                          "task-core-inventory.yaml")
        with self._open_file(task_core_inv_file) as inv_file:
            inv = inventory.task_core_inventory(self.stack_outputs)
            yaml.safe_dump(inv, inv_file, default_flow_style=False)

        directord_inv_file = os.path.join(task_core_dir,
                                          "directord-inventory.yaml")
        with self._open_file(directord_inv_file) as inv_file:
            inv = inventory.directord_inventory(self.stack_outputs)
            yaml.safe_dump(inv, inv_file, default_flow_style=False)

    def write_config(self, stack, name, config_dir, config_type=None):
        # Get role data:
        role_data = self.stack_outputs.get('RoleData', {})
        role_group_vars = self.stack_outputs.get('RoleGroupVars', {})
        role_host_vars = self.stack_outputs.get('AnsibleHostVarsMap', {})
        for role_name, role in role_data.items():
            role_path = os.path.join(config_dir, role_name)
            self._mkdir(role_path)
            for config in config_type or role.keys():
                if config in constants.EXTERNAL_TASKS:
                    # external tasks are collected globally, not per-role
                    continue
                if config == 'step_config':
                    filepath = os.path.join(role_path, 'step_config.pp')
                    with self._open_file(filepath) as step_config:
                        step_config.write(role[config])
                elif config == 'param_config':
                    filepath = os.path.join(role_path, 'param_config.json')
                    with self._open_file(filepath) as param_config:
                        param_config.write(json.dumps(role[config]))
                else:
                    # NOTE(emilien): Move this condition to the
                    # upper level once THT is adapted for all tasks to be
                    # run per step.
                    # We include it here to allow the CI to pass until THT
                    # changed is not merged.
                    if config in constants.PER_STEP_TASKS.keys():
                        for i in range(len(constants.PER_STEP_TASKS[config])):
                            filepath = os.path.join(role_path, '%s_step%s.yaml'
                                                    % (config, i))
                            self._write_tasks_per_step(
                                role[config], filepath, i,
                                constants.PER_STEP_TASKS[config][i])

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
        for config_name, config in role_config.items():

            # External tasks are in RoleConfig and not defined per role.
            # So we don't use the RoleData to create the per step playbooks.
            if config_name in constants.EXTERNAL_TASKS:
                for i in range(constants.DEFAULT_STEPS_MAX):
                    filepath = os.path.join(config_dir,
                                            '%s_step%s.yaml'
                                            % (config_name, i))
                    self._write_tasks_per_step(config, filepath, i)

            conf_path = os.path.join(config_dir, config_name)
            # Add .yaml extension only if there's no extension already
            if '.' not in conf_path:
                conf_path = conf_path + ".yaml"
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
                warnings.warn('Determining grandparent resource name for '
                              'deployment %s. Ensure the name property is '
                              'set on the deployment resource in the '
                              'templates.' % deployment_ref)

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
                grandparent_stack = self.client.stacks.get(
                    parent_stack, resolve_outputs=False).parent
                resources = self.client.resources.list(
                    grandparent_stack,
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
                                 '(may be blacklisted)', server_id)
                # continue the loop as this server_id is probably excluded
                continue
            except Exception as err:
                err_msg = ('Error retrieving server name from this server_id: '
                           '%s with this error: %s' % server_id, err)
                raise Exception(err_msg)

            role = self.get_role_from_server_id(stack, server_id)
            server_pre_network = server_deployment_names.setdefault(
                server_names[server_id], {}).setdefault(
                'pre_network', [])
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
            elif 'PreNetworkConfig' in deployment.physical_resource_id:
                if deployment_name not in server_pre_network:
                    server_pre_network.append(deployment_name)
            else:
                if deployment_name not in server_pre_deployments:
                    server_pre_deployments.append(deployment_name)

        # Make sure server_roles is populated b/c it won't be if there are no
        # server deployments.
        for server_name, server_id in server_ids.items():
            server_roles.setdefault(
                server_name,
                self.get_role_from_server_id(stack, server_id))

        env, templates_path = self.get_jinja_env(config_dir)

        templates_dest = os.path.join(config_dir, 'templates')
        self._mkdir(templates_dest)
        shutil.copyfile(os.path.join(templates_path, 'heat-config.j2'),
                        os.path.join(templates_dest, 'heat-config.j2'))

        group_vars_dir = os.path.join(config_dir, 'group_vars')
        self._mkdir(group_vars_dir)

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
                if not (isinstance(data, str) or
                        isinstance(data, str)):
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

        self.render_task_core(name, config_dir, role_data, server_roles,
                              role_group_vars, role_config)

        # Render host_vars
        for server in server_names.values():
            host_var_server_path = os.path.join(host_vars_dir, server)
            host_var_server_template = env.get_template('host_var_server.j2')
            role = server_roles[server]
            ansible_host_vars = (
                yaml.safe_dump(
                    role_host_vars[role][server],
                    default_flow_style=False) if role_host_vars else None)

            pre_network = server_deployment_names.get(
                server, {}).get('pre_network', [])
            pre_deployments = server_deployment_names.get(
                server, {}).get('pre_deployments', [])
            post_deployments = server_deployment_names.get(
                server, {}).get('post_deployments', [])

            with open(host_var_server_path, 'w') as f:
                template_data = host_var_server_template.render(
                    role=role,
                    pre_network=pre_network,
                    pre_deployments=pre_deployments,
                    post_deployments=post_deployments,
                    ansible_host_vars=ansible_host_vars)
                self.validate_config(template_data, host_var_server_path)
                f.write(template_data)

        # Render NetworkConfig data
        self.render_network_config(config_dir)

        shutil.copyfile(
            os.path.join(templates_path, 'deployments.yaml'),
            os.path.join(config_dir, 'deployments.yaml'))

        self.log.info("The TripleO configuration has been successfully "
                      "generated into: %s", config_dir)
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
                      "%s", config_dir)
        self.write_config(stack, name, config_dir, config_type)
        self.snapshot_config_dir(git_repo, commit_message)
        return config_dir


def get_overcloud_config(swift=None, heat=None,
                         container=constants.DEFAULT_CONTAINER_NAME,
                         container_config=constants.CONFIG_CONTAINER_NAME,
                         config_dir=None, config_type=None,
                         preserve_config=False):
    if heat is None:
        raise RuntimeError('Should provide orchestration client to fetch '
                           ' TripleO config')
    if not config_dir:
        config_dir = tempfile.mkdtemp(prefix='tripleo-',
                                      suffix='-config')

    config = Config(heat)
    message = "Automatic commit with fresh config download\n\n"

    config_path = config.download_config(container, config_dir,
                                         config_type,
                                         preserve_config_dir=True,
                                         commit_message=message)

    if not preserve_config:
        if os.path.exists(config_path):
            shutil.rmtree(config_path)
