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

from heatclient import exc as heat_exc
from mistral.workflow import utils as mistral_workflow_utils

from tripleo_common.actions import base
from tripleo_common.actions import templates
from tripleo_common import constants
from tripleo_common.utils import parameters
from tripleo_common.utils import passwords as password_utils

LOG = logging.getLogger(__name__)


class GetParametersAction(templates.ProcessTemplatesAction):
    """Gets list of available heat parameters."""

    def run(self):
        processed_data = super(GetParametersAction, self).run()

        # If we receive a 'Result' instance it is because the parent action
        # had an error.
        if isinstance(processed_data, mistral_workflow_utils.Result):
            return processed_data

        processed_data['show_nested'] = True

        # respect previously user set param values
        wc = self._get_workflow_client()
        wf_env = wc.environments.get(self.container)
        orc = self._get_orchestration_client()

        params = wf_env.variables.get('parameter_defaults')

        fields = {
            'template': processed_data['template'],
            'files': processed_data['files'],
            'environment': processed_data['environment'],
            'show_nested': True
        }
        return {
            'heat_resource_tree': orc.stacks.validate(**fields),
            'mistral_environment_parameters': params,
        }


class ResetParametersAction(base.TripleOAction):
    """Provides method to delete user set parameters."""

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(ResetParametersAction, self).__init__()
        self.container = container

    def run(self):
        wc = self._get_workflow_client()
        wf_env = wc.environments.get(self.container)

        if 'parameter_defaults' in wf_env.variables:
            wf_env.variables.pop('parameter_defaults')

        env_kwargs = {
            'name': wf_env.name,
            'variables': wf_env.variables
        }
        wc.environments.update(**env_kwargs)
        return wf_env


class UpdateParametersAction(base.TripleOAction):
    """Updates Mistral Environment with parameters."""

    def __init__(self, parameters,
                 container=constants.DEFAULT_CONTAINER_NAME):
        super(UpdateParametersAction, self).__init__()
        self.container = container
        self.parameters = parameters

    def run(self):
        wc = self._get_workflow_client()
        wf_env = wc.environments.get(self.container)
        if 'parameter_defaults' not in wf_env.variables:
            wf_env.variables['parameter_defaults'] = {}
        wf_env.variables['parameter_defaults'].update(self.parameters)
        env_kwargs = {
            'name': wf_env.name,
            'variables': wf_env.variables
        }
        wc.environments.update(**env_kwargs)
        return wf_env


class UpdateRoleParametersAction(UpdateParametersAction):
    """Updates role related parameters in Mistral Environment ."""

    def __init__(self, role, container=constants.DEFAULT_CONTAINER_NAME):
        super(UpdateRoleParametersAction, self).__init__(parameters=None,
                                                         container=container)
        self.role = role

    def run(self):
        baremetal_client = self._get_baremetal_client()
        compute_client = self._get_compute_client()
        self.parameters = parameters.set_count_and_flavor_params(
            self.role, baremetal_client, compute_client)
        return super(UpdateRoleParametersAction, self).run()


class GeneratePasswordsAction(base.TripleOAction):
    """Generates passwords needed for Overcloud deployment

    This method generates passwords and ensures they are stored in the
    mistral environment associated with a plan.  This method respects
    previously generated passwords and adds new passwords as necessary.
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        self.container = container

    def run(self):

        orchestration = self._get_orchestration_client()
        wc = self._get_workflow_client()
        try:
            wf_env = wc.environments.get(self.container)
        except Exception:
            msg = "Error retrieving mistral environment: %s" % self.container
            LOG.exception(msg)
            return mistral_workflow_utils.Result("", msg)

        try:
            stack_env = orchestration.stacks.environment(
                stack_id=self.container)
        except heat_exc.HTTPNotFound:
            stack_env = None

        passwords = password_utils.generate_overcloud_passwords(wc, stack_env)

        # if passwords don't yet exist in mistral environment
        if 'passwords' not in wf_env.variables:
            wf_env.variables['passwords'] = {}

        # ensure all generated passwords are present in mistral env,
        # but respect any values previously generated and stored
        for name, password in passwords.items():
            if name not in wf_env.variables['passwords']:
                wf_env.variables['passwords'][name] = password

        env_kwargs = {
            'name': wf_env.name,
            'variables': wf_env.variables,
        }

        wc.environments.update(**env_kwargs)

        return wf_env.variables['passwords']
