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
import time

from heatclient.common import template_utils
from heatclient import exc as heat_exc
from mistral.workflow import utils as mistral_workflow_utils

from tripleo_common.actions import base
from tripleo_common.actions import templates
from tripleo_common import constants
from tripleo_common.update import PackageUpdateManager

LOG = logging.getLogger(__name__)


class ClearBreakpointsAction(base.TripleOAction):
    def __init__(self, stack_id, refs):
        super(ClearBreakpointsAction, self).__init__()
        self.stack_id = stack_id
        self.refs = refs

    def run(self):
        heat = self.get_orchestration_client()
        nova = self.get_compute_client()
        update_manager = PackageUpdateManager(
            heat, nova, self.stack_id, stack_fields={})
        update_manager.clear_breakpoints(self.refs)


class CancelStackUpdateAction(base.TripleOAction):
    def __init__(self, stack_id):
        super(CancelStackUpdateAction, self).__init__()
        self.stack_id = stack_id

    def run(self):
        heat = self.get_orchestration_client()
        nova = self.get_compute_client()
        update_manager = PackageUpdateManager(
            heat, nova, self.stack_id, stack_fields={})
        update_manager.cancel()


class UpdateStackAction(templates.ProcessTemplatesAction):

    def __init__(self, timeout, container=constants.DEFAULT_CONTAINER_NAME):
        super(UpdateStackAction, self).__init__(container)
        self.timeout_mins = timeout

    def run(self):
        # get the stack. Error if doesn't exist
        heat = self.get_orchestration_client()
        try:
            stack = heat.stacks.get(self.container)
        except heat_exc.HTTPNotFound:
            msg = "Error retrieving stack: %s" % self.container
            LOG.exception(msg)
            return mistral_workflow_utils.Result(error=msg)

        parameters = dict()
        timestamp = int(time.time())
        parameters['DeployIdentifier'] = timestamp
        parameters['UpdateIdentifier'] = timestamp
        parameters['StackAction'] = 'UPDATE'

        wc = self.get_workflow_client()
        try:
            wf_env = wc.environments.get(self.container)
        except Exception:
            msg = "Error retrieving mistral environment: %s" % self.container
            LOG.exception(msg)
            return mistral_workflow_utils.Result(error=msg)

        if 'parameter_defaults' not in wf_env.variables:
            wf_env.variables['parameter_defaults'] = {}
        wf_env.variables['parameter_defaults'].update(parameters)
        env_kwargs = {
            'name': wf_env.name,
            'variables': wf_env.variables,
        }

        # store params changes back to db before call to process templates
        wc.environments.update(**env_kwargs)

        # process all plan files and create or update a stack
        processed_data = super(UpdateStackAction, self).run()

        # If we receive a 'Result' instance it is because the parent action
        # had an error.
        if isinstance(processed_data, mistral_workflow_utils.Result):
            return processed_data

        stack_args = processed_data.copy()

        env = stack_args.get('environment', {})
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
        stack_args['environment'] = env

        stack_args['timeout_mins'] = self.timeout_mins
        stack_args['existing'] = 'true'

        LOG.info("Performing Heat stack update")
        LOG.info('updating stack: %s', stack.stack_name)
        return heat.stacks.update(stack.id, **stack_args)
