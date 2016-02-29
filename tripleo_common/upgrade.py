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

import logging
import os

from heatclient.common import template_utils

LOG = logging.getLogger(__name__)
TEMPLATE_NAME = 'overcloud-without-mergepy.yaml'
UPGRADE_ENVIRONMENT_NAME = 'major-upgrade-pacemaker.yaml'
STACK_TIMEOUT_DEFAULT = 240


class StackUpgradeManager(object):
    def __init__(self, heatclient, stack_id,
                 tht_dir=None, environment_files=None):
        self.stack = heatclient.stacks.get(stack_id)
        self.tht_dir = tht_dir
        self.environment_files = environment_files
        self.heatclient = heatclient

    def upgrade(self, timeout_mins=STACK_TIMEOUT_DEFAULT):
        stack_params = {}

        tpl_files, template = template_utils.get_template_contents(
            template_file=os.path.join(self.tht_dir, TEMPLATE_NAME))
        env_paths = []
        if self.environment_files:
            env_paths.extend(self.environment_files)
        env_paths.append(os.path.join(self.tht_dir, 'environments',
                         UPGRADE_ENVIRONMENT_NAME))
        env_files, env = (
            template_utils.process_multiple_environments_and_files(
                env_paths=env_paths))
        fields = {
            'existing': True,
            'stack_id': self.stack.id,
            'template': template,
            'files': dict(list(tpl_files.items()) +
                          list(env_files.items())),
            'environment': env,
            'parameters': stack_params,
            'timeout_mins': timeout_mins,
        }

        LOG.info('upgrading stack: %s', self.stack.stack_name)
        LOG.debug('stack upgrade params: %s', fields)
        self.heatclient.stacks.update(**fields)

    def get_status(self):
        self.stack = self.heatclient.stacks.get(self.stack.id)
        status = self.stack.status
        LOG.debug('%s status: %s', self.stack.stack_name, status)
        return status
