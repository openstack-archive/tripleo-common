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
import re
import shutil
import time

from heatclient.common import template_utils
from tripleo_common import libutils
from tripleo_common import stack_update
from tuskarclient.common import utils as tuskarutils

LOG = logging.getLogger(__name__)
TEMPLATE_NAME = 'overcloud-without-mergepy.yaml'
REGISTRY_NAME = "overcloud-resource-registry-puppet.yaml"


class PackageUpdateManager(stack_update.StackUpdateManager):
    def __init__(self, heatclient, novaclient, stack_id, tuskarclient=None,
                 plan_id=None, tht_dir=None, environment_files=None):
        stack = heatclient.stacks.get(stack_id)
        self.tuskarclient = tuskarclient
        self.plan_id = plan_id
        self.tht_dir = tht_dir
        self.hook_resource = 'UpdateDeployment'
        if self.tuskarclient:
            self.plan = tuskarutils.find_resource(self.tuskarclient.plans,
                                                  self.plan_id)
        self.environment_files = environment_files
        super(PackageUpdateManager, self).__init__(
            heatclient=heatclient, novaclient=novaclient, stack=stack,
            hook_type='pre-update', nested_depth=5,
            hook_resource=self.hook_resource)

    def update(self):
        # time rounded to seconds, we explicitly convert to string because of
        # tuskar
        timestamp = str(int(time.time()))

        if self.tuskarclient:
            stack_params = self._set_update_params(timestamp)
            self.tht_dir = libutils.save_templates(
                self.tuskarclient.plans.templates(self.plan.uuid))
            tpl_name = 'plan.yaml'
            env_name = 'environment.yaml'
        else:
            tpl_name = TEMPLATE_NAME
            env_name = REGISTRY_NAME
            stack_params = {'UpdateIdentifier': timestamp}

        try:
            tpl_files, template = template_utils.get_template_contents(
                template_file=os.path.join(self.tht_dir, tpl_name))
            env_paths = [os.path.join(self.tht_dir, env_name)]
            if self.environment_files:
                env_paths.extend(self.environment_files)
            env_files, env = (
                template_utils.process_multiple_environments_and_files(
                    env_paths=env_paths))
            template_utils.deep_update(env, {
                'resource_registry': {
                    'resources': {
                        '*': {
                            '*': {
                                self.hook_resource: {'hooks': 'pre-update'}
                            }
                        }
                    }
                }
            })
            fields = {
                'existing': True,
                'stack_id': self.stack.id,
                'template': template,
                'files': dict(list(tpl_files.items()) +
                              list(env_files.items())),
                'environment': env,
                'parameters': stack_params
            }

            LOG.info('updating stack: %s', self.stack.stack_name)
            LOG.debug('stack update params: %s', fields)
            self.heatclient.stacks.update(**fields)
        finally:
            if self.tuskarclient:
                if LOG.isEnabledFor(logging.DEBUG):
                    LOG.debug("Tuskar templates saved in %s", self.tht_dir)
                else:
                    shutil.rmtree(self.tht_dir)

    def _set_update_params(self, timestamp):
        # set new update timestamp for each role
        params = {}
        for param in self.plan.parameters:
            if re.match(r".*::UpdateIdentifier", param['name']):
                params[param['name']] = timestamp
        return params
