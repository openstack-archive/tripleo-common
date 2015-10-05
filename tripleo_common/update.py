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
import time

from heatclient.common import template_utils
from tripleo_common import stack_update

LOG = logging.getLogger(__name__)
TEMPLATE_NAME = 'overcloud-without-mergepy.yaml'
UPDATE_RESOURCE_NAME = 'UpdateDeployment'


def add_breakpoints_cleanup_into_env(env):
    template_utils.deep_update(env, {
        'resource_registry': {
            'resources': {'*': {'*': {UPDATE_RESOURCE_NAME: {'hooks': []}}}}
        }
    })


class PackageUpdateManager(stack_update.StackUpdateManager):
    def __init__(self, heatclient, novaclient, stack_id,
                 tht_dir=None, environment_files=None):
        stack = heatclient.stacks.get(stack_id)
        self.tht_dir = tht_dir
        self.environment_files = environment_files
        super(PackageUpdateManager, self).__init__(
            heatclient=heatclient, novaclient=novaclient, stack=stack,
            hook_type='pre-update', nested_depth=5,
            hook_resource=UPDATE_RESOURCE_NAME)

    def update(self):
        # time rounded to seconds
        timestamp = int(time.time())

        stack_params = {'UpdateIdentifier': timestamp}

        tpl_files, template = template_utils.get_template_contents(
            template_file=os.path.join(self.tht_dir, TEMPLATE_NAME))
        env_paths = []
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
                            UPDATE_RESOURCE_NAME: {'hooks': 'pre-update'}
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
