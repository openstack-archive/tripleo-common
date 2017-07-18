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

import fnmatch
import logging
import yaml

from mistral_lib import actions
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import plan as plan_utils

LOG = logging.getLogger(__name__)


class GetCapabilitiesAction(base.TripleOAction):
    """Gets list of available heat environments

    Parses the capabilities_map.yaml file in a given plan and
    returns a list of environments

    :param container: name of the swift container / plan name
    :return: list of environment files in swift container
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(GetCapabilitiesAction, self).__init__()
        self.container = container

    def run(self, context):
        try:
            swift = self.get_object_client(context)
            map_file = swift.get_object(
                self.container, 'capabilities-map.yaml')
            capabilities = yaml.safe_load(map_file[1])
        except Exception:
            err_msg = (
                "Error parsing capabilities-map.yaml.")
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)
        try:
            container_files = swift.get_container(self.container)
            container_file_list = [entry['name'] for entry
                                   in container_files[1]]
        except Exception as swift_err:
            err_msg = ("Error retrieving plan files: %s" % swift_err)
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        selected_envs = [item['path'] for item in env['environments']
                         if 'path' in item]

        # extract environment files
        plan_environments = []
        for env_group in capabilities['topics']:
            for envs in env_group['environment_groups']:
                for files in envs['environments']:
                    file = files.get('file')
                    if file:
                        plan_environments.append(file)

        # parse plan for environment files
        env_files = fnmatch.filter(
            container_file_list, '*environments/*.yaml')
        env_user_files = fnmatch.filter(
            container_file_list, '*user-environment.yaml')

        outstanding_envs = list(set(env_files).union(
            env_user_files) - set(plan_environments))

        # change capabilities format
        data_to_return = {}

        for topic in capabilities['topics']:
            title = topic.get('title', '_title_holder')
            data_to_return[title] = topic
            for eg in topic['environment_groups']:
                for env in eg['environments']:
                    if selected_envs and env.get('file') in selected_envs:
                        env['enabled'] = True
                    else:
                        env['enabled'] = False

        # add custom environment files
        other_environments = []
        for env in outstanding_envs:
            flag = selected_envs and env in selected_envs
            new_env = {
                "description": "Enable %s environment" % env,
                "enabled": flag,
                "file": env,
                "title": env,
            }
            other_environments.append(new_env)
        other_environments.sort(key=lambda x: x['file'])

        other_environment_groups = []
        for group in other_environments:
            new_group = {
                "description": None,
                "environments": [group],
                "title": group['file'],
            }
            other_environment_groups.append(new_group)

        other_environments_topic_dict = {
            "description": None,
            "title": "Other",
            "environment_groups": other_environment_groups
        }

        other_environments_topic = {
            "Other": other_environments_topic_dict
        }
        data_to_return.update(other_environments_topic)

        return data_to_return


class UpdateCapabilitiesAction(base.TripleOAction):
    """Updates plan environment with selected environments

    Takes a list of environment files and depending on the value of the
    enabled flag, adds or removes them from the plan environment.

    :param environments: map of environments {'environment_path': True}
                         the value passed can be false for disabled
                         environments, these will be removed from the
                         plan environment.
    :param container: name of the swift container / plan name
    :param purge_missing: remove any environments from the plan environment
                          that aren't included in the environments map
                          defaults to False
    :return: the updated plan environment
    """

    def __init__(self, environments,
                 container=constants.DEFAULT_CONTAINER_NAME,
                 purge_missing=False):
        super(UpdateCapabilitiesAction, self).__init__()
        self.container = container
        self.environments = environments
        self.purge_missing = purge_missing

    def run(self, context):
        swift = self.get_object_client(context)

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        for k, v in self.environments.items():
            found = False
            if {'path': k} in env['environments']:
                found = True
            if v:
                if not found:
                    env['environments'].append({'path': k})
            else:
                if found:
                    env['environments'].remove({'path': k})

        if self.purge_missing:
            for e in env['environments']:
                if e.get('path') not in self.environments:
                    env['environments'].remove(e)

        self.cache_delete(context, self.container, "tripleo.parameters.get")

        try:
            plan_utils.put_env(swift, env)
        except swiftexceptions.ClientException as err:
            err_msg = "Error uploading to container: %s" % err
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        return env
