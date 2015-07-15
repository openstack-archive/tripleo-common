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

import logging
import os
import shutil

from heatclient.common import template_utils
from tripleo_common import libutils
from tuskarclient.common import utils as tuskarutils

LOG = logging.getLogger(__name__)
TEMPLATE_NAME = 'overcloud-without-mergepy.yaml'
REGISTRY_NAME = "overcloud-resource-registry-puppet.yaml"


class ScaleManager(object):
    def __init__(self, heatclient, stack_id, tuskarclient=None, plan_id=None,
                 tht_dir=None, environment_files=None):
        self.tuskarclient = tuskarclient
        self.heatclient = heatclient
        self.stack_id = stack_id
        self.tht_dir = tht_dir
        self.environment_files = environment_files
        if self.tuskarclient:
            self.plan = tuskarutils.find_resource(self.tuskarclient.plans,
                                                  plan_id)

    def scaleup(self, role, num):
        LOG.debug('updating role %s count to %d', role, num)
        param_name = '{0}::count'.format(role)
        param = next(x for x in self.plan.parameters if
                     x['name'] == param_name)
        if num < int(param['value']):
            raise ValueError("Role %s has already %s nodes, can't set lower "
                             "value" % (role, param['value']))
        self.plan = self.tuskarclient.plans.patch(
            self.plan.uuid,
            [{'name': param_name, 'value': str(num)}])
        self._update_stack()

    def scaledown(self, instances):
        resources = self.heatclient.resources.list(self.stack_id,
                                                   nested_depth=5)
        resources_by_role = {}
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
            # get tuskar role name from resource_type,
            # resource_type is in format like "Tuskar::Compute-1"
            role = role_resource.resource_type.rsplit('::', 1)[-1]
            if role not in resources_by_role:
                resources_by_role[role] = []
            resources_by_role[role].append(role_resource)

        if instance_list:
            raise ValueError(
                "Couldn't find following instances in stack %s: %s" %
                (self.stack_id, ','.join(instance_list)))

        # decrease count for each role (or resource group) and set removal
        # policy for each resource group
        if self.tuskarclient:
            stack_params = self._get_removal_params_from_plan(
                resources_by_role)
        else:
            stack_params = self._get_removal_params_from_heat(
                resources_by_role)

        self._update_stack(parameters=stack_params)

    def _update_stack(self, parameters={}):
        if self.tuskarclient:
            self.tht_dir = libutils.save_templates(
                self.tuskarclient.plans.templates(self.plan.uuid))
            tpl_name = 'plan.yaml'
            env_name = 'environment.yaml'
        else:
            tpl_name = TEMPLATE_NAME
            env_name = REGISTRY_NAME

        try:
            tpl_files, template = template_utils.get_template_contents(
                template_file=os.path.join(self.tht_dir, tpl_name))
            env_paths = [os.path.join(self.tht_dir, env_name)]
            if self.environment_files:
                env_paths.extend(self.environment_files)
            env_files, env = (
                template_utils.process_multiple_environments_and_files(
                    env_paths=env_paths))
            fields = {
                'existing': True,
                'stack_id': self.stack_id,
                'template': template,
                'files': dict(list(tpl_files.items()) +
                              list(env_files.items())),
                'environment': env,
                'parameters': parameters
            }

            LOG.debug('stack update params: %s', fields)
            self.heatclient.stacks.update(**fields)
        finally:
            if self.tuskarclient:
                if LOG.isEnabledFor(logging.DEBUG):
                    LOG.debug("Tuskar templates saved in %s", self.tht_dir)
                else:
                    shutil.rmtree(self.tht_dir)

    def _get_removal_params_from_plan(self, resources_by_role):
        patch_params = []
        stack_params = {}
        for role, role_resources in resources_by_role.items():
            param_name = "{0}::count".format(role)
            old_count = next(x['value'] for x in self.plan.parameters if
                             x['name'] == param_name)
            count = max(int(old_count) - len(role_resources), 0)
            patch_params.append({'name': param_name, 'value': str(count)})
            # add instance resource names into removal_policies
            # so heat knows which instances should be removed
            removal_param = "{0}::removal_policies".format(role)
            stack_params[removal_param] = [{
                'resource_list': [r.resource_name for r in role_resources]
            }]

        LOG.debug('updating plan %s: %s', self.plan.uuid, patch_params)
        self.plan = self.tuskarclient.plans.patch(self.plan.uuid, patch_params)
        return stack_params

    def _get_removal_params_from_heat(self, resources_by_role):
        stack_params = {}
        stack = self.heatclient.stacks.get(self.stack_id)
        for role, role_resources in resources_by_role.items():
            param_name = "{0}Count".format(role)
            old_count = next(v for k, v in stack.parameters.iteritems() if
                             k == param_name)
            count = max(int(old_count) - len(role_resources), 0)
            stack_params[param_name] = str(count)
            # add instance resource names into removal_policies
            # so heat knows which instances should be removed
            removal_param = "{0}RemovalPolicies".format(role)
            stack_params[removal_param] = [{
                'resource_list': [r.resource_name for r in role_resources]
            }]

        return stack_params
