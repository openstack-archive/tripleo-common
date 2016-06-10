# Copyright 2106 Red Hat, Inc.
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
import yaml

from mistral.workflow import utils as mistral_workflow_utils

from tripleo_common.actions import base
from tripleo_common import constants

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

    def run(self):
        environments = {}
        try:
            map_file = self._get_object_client().get_object(
                self.container, 'capabilities-map.yaml')
            capabilities = yaml.safe_load(map_file[1])
        except Exception:
            err_msg = (
                "Error parsing capabilities-map.yaml.")
            LOG.exception(err_msg)
            return mistral_workflow_utils.Result(
                None,
                err_msg
            )
        # identify all environments
        for topic in capabilities['topics']:
            for eg in topic['environment_groups']:
                for env in eg['environments']:
                    environments[env['file']] = {'enabled': False}
        try:
            mistral_client = self._get_workflow_client()
            mistral_env = mistral_client.environments.get(self.container)
        except Exception as mistral_err:
            err_msg = ("Error retrieving mistral "
                       "environment. %s" % mistral_err)
            LOG.exception(err_msg)
            return mistral_workflow_utils.Result(
                None,
                err_msg
            )

        selected_envs = [item['path'] for item in
                         mistral_env.variables['environments']
                         if 'path' in item]
        for item in selected_envs:
            if item in environments:
                environments[item]['enabled'] = True
            else:
                environments[item] = {'enabled': False}

        return environments


class UpdateCapabilitiesAction(base.TripleOAction):
    """Updates Mistral Environment with selected environments

    Takes a list of environment files and depending on the value of the
    enabled flag, adds or removes them from the Mistral Environment.

    :param environments: list of environments
    :param container: name of the swift container / plan name
    :return: the updated mistral environment
    """

    def __init__(self, environments,
                 container=constants.DEFAULT_CONTAINER_NAME):
        super(UpdateCapabilitiesAction, self).__init__()
        self.container = container
        self.environments = environments

    def run(self):
        mistral_client = self._get_workflow_client()
        mistral_env = None
        try:
            mistral_env = mistral_client.environments.get(self.container)
        except Exception as mistral_err:
            err_msg = (
                "Error retrieving mistral "
                "environment. %s" % mistral_err)
            LOG.exception(err_msg)
            return mistral_workflow_utils.Result(
                None,
                err_msg
            )

        for k, v in self.environments.items():
            if v.get('enabled', False):
                mistral_env.variables['environments'].append(
                    {'path': k}
                )
            else:
                # see if it resides in mistral env and if so, remove it
                if {'path': k} in mistral_env.variables['environments']:
                    mistral_env.variables['environments'].pop({'path': k})

        env_kwargs = {
            'name': mistral_env.name,
            'variables': mistral_env.variables
        }
        try:
            mistral_client.environments.update(**env_kwargs)
        except Exception as mistral_err:
            err_msg = (
                "Error retrieving mistral "
                "environment. %s" % mistral_err)
            LOG.exception(err_msg)
            return mistral_workflow_utils.Result(
                None,
                err_msg
            )
        return mistral_env
