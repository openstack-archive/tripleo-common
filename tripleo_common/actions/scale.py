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
import collections
import logging

from mistral_lib import actions

from tripleo_common.actions import parameters as parameters_actions
from tripleo_common.actions import templates
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


class ScaleDownAction(templates.ProcessTemplatesAction):
    """Deletes overcloud nodes

    Before calling this method, ensure you have updated the plan
    with any templates or environment files as needed.
    """

    def __init__(self, timeout, nodes=[],
                 container=constants.DEFAULT_CONTAINER_NAME):
        self.nodes = nodes
        self.timeout_mins = timeout
        super(ScaleDownAction, self).__init__(container)

    def _update_stack(self, parameters={},
                      timeout_mins=constants.STACK_TIMEOUT_DEFAULT,
                      context=None):
        # TODO(rbrady): migrate _update_stack to it's own action and update
        # the workflow for scale down

        # update the plan parameters with the scaled down parameters
        update_params_action = parameters_actions.UpdateParametersAction(
            parameters, self.container)
        updated_plan = update_params_action.run(context)
        if isinstance(updated_plan, actions.Result):
            return updated_plan

        processed_data = super(ScaleDownAction, self).run(context)
        if isinstance(processed_data, actions.Result):
            return processed_data

        update.add_breakpoints_cleanup_into_env(processed_data['environment'])

        fields = processed_data.copy()
        fields['timeout_mins'] = timeout_mins
        fields['existing'] = True
        # As we do a PATCH update when deleting nodes, parameters set for a
        # stack before upgrade to newton (ex. ComputeRemovalPolicies),
        # would still take precedence over the ones set in parameter_defaults
        # after upgrade. Clear these parameters for backward compatibility.
        fields['clear_parameters'] = list(parameters.keys())

        LOG.debug('stack update params: %s', fields)
        self.get_orchestration_client(context).stacks.update(self.container,
                                                             **fields)

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

    def run(self, context):
        heatclient = self.get_orchestration_client(context)
        resources = heatclient.resources.list(self.container, nested_depth=5)
        resources_by_role = collections.defaultdict(list)
        instance_list = list(self.nodes)
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
                (self.container, ','.join(instance_list)))

        # decrease count for each role (or resource group) and set removal
        # policy for each resource group
        stack_params = self._get_removal_params_from_heat(
            resources_by_role, resources)

        return self._update_stack(parameters=stack_params, context=context)
