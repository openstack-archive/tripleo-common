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
import time

from heatclient.common import template_utils

from tripleo_common import _stack_update
from tripleo_common import constants

LOG = logging.getLogger(__name__)


def add_breakpoints_cleanup_into_env(env):
    template_utils.deep_update(env, {
        'resource_registry': {
            'resources': {'*': {'*': {
                constants.UPDATE_RESOURCE_NAME: {'hooks': []}}}}
        }
    })


class PackageUpdateManager(_stack_update.StackUpdateManager):
    def __init__(self, heatclient, novaclient, stack_id, stack_fields):
        stack = heatclient.stacks.get(stack_id)
        self.stack_fields = stack_fields
        super(PackageUpdateManager, self).__init__(
            heatclient=heatclient, novaclient=novaclient, stack=stack,
            hook_type='pre-update', nested_depth=5,
            hook_resource=constants.UPDATE_RESOURCE_NAME)

    def update(self, timeout_mins=constants.STACK_TIMEOUT_DEFAULT):
        env = {}
        if 'environment' in self.stack_fields:
            env = self.stack_fields['environment']

        template_utils.deep_update(env, {
            'resource_registry': {
                'resources': {
                    '*': {
                        '*': {
                            constants.UPDATE_RESOURCE_NAME: {
                                'hooks': 'pre-update'}
                        }
                    }
                }
            }
        })

        # time rounded to seconds
        timestamp = int(time.time())

        stack_params = {
            'DeployIdentifier': timestamp,
            'UpdateIdentifier': timestamp,
            'StackAction': 'UPDATE'
        }
        template_utils.deep_update(env, {'parameter_defaults': stack_params})

        self.stack_fields['environment'] = env

        fields = {
            'existing': True,
            'stack_id': self.stack.id,
            'template': self.stack_fields['template'],
            'files': self.stack_fields['files'],
            'environment': self.stack_fields['environment'],
            'timeout_mins': timeout_mins,
            'stack_name': self.stack_fields['stack_name'],
        }

        LOG.info('updating stack: %s', self.stack.stack_name)
        LOG.debug('stack update params: %s', fields)
        self.heatclient.stacks.update(**fields)
