# Copyright 2015 Red Hat, Inc.
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

import collections
import logging
import os

from heatclient.common import template_utils

from tripleo_common import constants
from tripleo_common import update

LOG = logging.getLogger(__name__)


def get_group_resources_after_delete(groupname, res_to_delete, resources):
    group = next(res for res in resources if
                 res.resource_name == groupname and
                 res.resource_type == constants.RESOURCE_GROUP_TYPE)
    members = []
    for res in resources:
        stack_name, stack_id = next(
            x['href'] for x in res.links if
            x['rel'] == 'stack').rsplit('/', 2)[1:]
        # desired new count of nodes after delete operation should be
        # count of all existing nodes in ResourceGroup which are not
        # in set of nodes being deleted. Also nodes in any delete state
        # from a previous failed update operation are not included in
        # overall count (if such nodes exist)
        if (stack_id == group.physical_resource_id and
            res not in res_to_delete and
                not res.resource_status.startswith('DELETE')):

            members.append(res)

    return members


class ScaleManager(object):
    def __init__(self, heatclient, stack_id, tht_dir=None,
                 environment_files=None):
        self.heatclient = heatclient
        self.stack_id = stack_id
        self.tht_dir = tht_dir
        self.environment_files = environment_files

    def scaledown(self, instances):
        resources = self.heatclient.resources.list(self.stack_id,
                                                   nested_depth=5)
        resources_by_role = collections.defaultdict(list)
        instance_list = list(instances)
        for res in resources:
            try:
                instance_list.remove(res.physical_resource_id)
            except ValueError:
                continue

            stack_name, stack_id = next(
                x['href'] for x in res.links if
                x['rel'] == 'stack').rsplit('/', 2)[1:]
            # get resource to remove from resource group (it's parent resource
            # of nova server)
            role_resource = next(x for x in resources if
                                 x.physical_resource_id == stack_id)
            # get the role name which is parent resource name in Heat
            role = role_resource.parent_resource
            resources_by_role[role].append(role_resource)

        resources_by_role = dict(resources_by_role)

        if instance_list:
            raise ValueError(
                "Couldn't find following instances in stack %s: %s" %
                (self.stack_id, ','.join(instance_list)))

        # decrease count for each role (or resource group) and set removal
        # policy for each resource group
        stack_params = self._get_removal_params_from_heat(
            resources_by_role, resources)

        self._update_stack(parameters=stack_params)

    def _update_stack(self, parameters={},
                      timeout_mins=constants.STACK_TIMEOUT_DEFAULT):

        tpl_files, template = template_utils.get_template_contents(
            template_file=os.path.join(self.tht_dir,
                                       constants.OVERCLOUD_YAML_NAME))

        env_paths = []
        if self.environment_files:
            env_paths.extend(self.environment_files)
        env_files, env = (
            template_utils.process_multiple_environments_and_files(
                env_paths=env_paths))
        update.add_breakpoints_cleanup_into_env(env)

        fields = {
            'existing': True,
            'stack_id': self.stack_id,
            'template': template,
            'files': dict(list(tpl_files.items()) +
                          list(env_files.items())),
            'environment': env,
            'parameters': parameters,
            'timeout_mins': timeout_mins
        }

        LOG.debug('stack update params: %s', fields)
        self.heatclient.stacks.update(**fields)

    def _get_removal_params_from_heat(self, resources_by_role, resources):
        stack_params = {}
        for role, role_resources in resources_by_role.items():
            param_name = "{0}Count".format(role)

            # get real count of nodes for each role. *Count stack parameters
            # can not be used because stack parameters return parameters
            # passed by user no matter if previous update operation succeeded
            # or not
            group_members = get_group_resources_after_delete(
                role, role_resources, resources)
            stack_params[param_name] = str(len(group_members))

            # add instance resource names into removal_policies
            # so heat knows which instances should be removed
            removal_param = "{0}RemovalPolicies".format(role)
            stack_params[removal_param] = [{
                'resource_list': [r.resource_name for r in role_resources]
            }]

        return stack_params
