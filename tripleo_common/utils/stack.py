# Copyright 2017 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import time

from heatclient.common import template_utils
from heatclient import exc as heat_exc
from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import template as templates

LOG = logging.getLogger(__name__)


def stack_update(swift, heat, timeout,
                 container=constants.DEFAULT_CONTAINER_NAME):
    # get the stack. Error if doesn't exist
    try:
        stack = heat.stacks.get(container)
    except heat_exc.HTTPNotFound:
        msg = "Error retrieving stack: %s" % container
        LOG.exception(msg)
        raise RuntimeError(msg)

    try:
        env = plan_utils.get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    update_env = {
        'parameter_defaults': {
            'DeployIdentifier': int(time.time()),
        },
    }

    noop_env = {
        'resource_registry': {
            'OS::TripleO::DeploymentSteps': 'OS::Heat::None',
        },
    }

    for output in stack.to_dict().get('outputs', {}):
        if output['output_key'] == 'RoleData':
            for role in output['output_value']:
                role_env = {
                    "OS::TripleO::Tasks::%sPreConfig" % role:
                    'OS::Heat::None',
                    "OS::TripleO::Tasks::%sPostConfig" % role:
                    'OS::Heat::None',
                }
                noop_env['resource_registry'].update(role_env)
    update_env.update(noop_env)
    template_utils.deep_update(env, update_env)
    try:
        plan_utils.put_env(swift, env)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error updating environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    # process all plan files and create or update a stack
    processed_data = templates.process_templates(
        swift, heat, container
    )
    stack_args = processed_data.copy()
    stack_args['timeout_mins'] = timeout

    LOG.info("Performing Heat stack update")
    LOG.info('updating stack: %s', stack.stack_name)
    return heat.stacks.update(stack.id, **stack_args)
