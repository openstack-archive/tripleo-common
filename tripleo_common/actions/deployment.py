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
import json
import logging
import time

from heatclient.common import deployment_utils
from heatclient import exc as heat_exc
from mistral.workflow import utils as mistral_workflow_utils
from mistralclient.api import base as mistralclient_exc
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common.actions import templates
from tripleo_common import constants
from tripleo_common.utils import overcloudrc

LOG = logging.getLogger(__name__)


class OrchestrationDeployAction(base.TripleOAction):

    def __init__(self, server_id, config, name, input_values=[],
                 action='CREATE', signal_transport='TEMP_URL_SIGNAL',
                 timeout=300, group='script'):
        super(OrchestrationDeployAction, self).__init__()
        self.server_id = server_id
        self.config = config
        self.input_values = input_values
        self.action = action
        self.name = name
        self.signal_transport = signal_transport
        self.timeout = timeout
        self.group = group

    def _extract_container_object_from_swift_url(self, swift_url):
        container_name = swift_url.split('/')[-2]
        object_name = swift_url.split('/')[-1].split('?')[0]
        return (container_name, object_name)

    def _build_sc_params(self, swift_url):
        source = {
            'config': self.config,
            'group': self.group,
        }
        return deployment_utils.build_derived_config_params(
            action=self.action,
            source=source,
            name=self.name,
            input_values=self.input_values,
            server_id=self.server_id,
            signal_transport=self.signal_transport,
            signal_id=swift_url
        )

    def _wait_for_data(self, container_name, object_name):
        body = None
        count_check = 0
        swift_client = self.get_object_client()
        while not body:
            headers, body = swift_client.get_object(
                container_name,
                object_name
            )
            count_check += 3
            if body or count_check > self.timeout:
                break
            time.sleep(3)

        return body

    def run(self):
        heat = self.get_orchestration_client()
        swift_client = self.get_object_client()

        swift_url = deployment_utils.create_temp_url(swift_client,
                                                     self.name,
                                                     self.timeout)
        container_name, object_name = \
            self._extract_container_object_from_swift_url(swift_url)

        params = self._build_sc_params(swift_url)
        config = heat.software_configs.create(**params)

        sd = heat.software_deployments.create(
            tenant_id='asdf',  # heatclient requires this
            config_id=config.id,
            server_id=self.server_id,
            action=self.action,
            status='IN_PROGRESS'
        )

        body = self._wait_for_data(container_name, object_name)

        # cleanup
        try:
            sd.delete()
            config.delete()
            swift_client.delete_object(container_name, object_name)
            swift_client.delete_container(container_name)
        except Exception as err:
            LOG.error("Error cleaning up heat deployment resources.", err)

        error = None
        if not body:
            body_json = {}
            error = "Timeout for heat deployment '%s'" % self.name
        else:
            body_json = json.loads(body)
            if body_json['deploy_status_code'] != 0:
                error = "Heat deployment failed for '%s'" % self.name

        return mistral_workflow_utils.Result(data=body_json, error=error)


class DeployStackAction(templates.ProcessTemplatesAction):
    """Deploys a heat stack."""

    def __init__(self, timeout, container=constants.DEFAULT_CONTAINER_NAME):
        super(DeployStackAction, self).__init__(container)
        self.timeout_mins = timeout

    def run(self):
        # check to see if the stack exists
        heat = self.get_orchestration_client()
        try:
            stack = heat.stacks.get(self.container)
        except heat_exc.HTTPNotFound:
            stack = None

        stack_is_new = stack is None

        # update StackAction, DeployIdentifier and UpdateIdentifier
        wc = self.get_workflow_client()
        wf_env = wc.environments.get(self.container)

        parameters = dict()
        parameters['DeployIdentifier'] = int(time.time())
        parameters['UpdateIdentifier'] = ''
        parameters['StackAction'] = 'CREATE' if stack_is_new else 'UPDATE'

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
        processed_data = super(DeployStackAction, self).run()

        # If we receive a 'Result' instance it is because the parent action
        # had an error.
        if isinstance(processed_data, mistral_workflow_utils.Result):
            return processed_data

        stack_args = processed_data.copy()
        stack_args['timeout_mins'] = self.timeout_mins

        if stack_is_new:
            swift_client = self.get_object_client()
            try:
                swift_client.copy_object(
                    "%s-swift-rings" % self.container, "swift-rings.tar.gz",
                    "%s-swift-rings/%s-%d" % (
                        self.container, "swift-rings.tar.gz", time.time()))
                swift_client.delete_object(
                    "%s-swift-rings" % self.container, "swift-rings.tar.gz")
            except swiftexceptions.ClientException:
                pass
            LOG.info("Perfoming Heat stack create")
            return heat.stacks.create(**stack_args)

        LOG.info("Performing Heat stack update")
        stack_args['existing'] = 'true'
        return heat.stacks.update(stack.id, **stack_args)


class OvercloudRcAction(base.TripleOAction):
    """Generate the overcloudrc and overcloudrc.v3 for a plan

    Given the name of a container, generate the overcloudrc files needed to
    access the overcloud via the CLI.

    no_proxy is optional and is a comma-separated string of hosts that
    shouldn't be proxied
    """

    def __init__(self, container, no_proxy=""):
        super(OvercloudRcAction, self).__init__()
        self.container = container
        self.no_proxy = no_proxy

    def run(self):
        orchestration_client = self.get_orchestration_client()
        workflow_client = self.get_workflow_client()

        try:
            stack = orchestration_client.stacks.get(self.container)
        except heat_exc.HTTPNotFound:
            error = (
                "The Heat stack {} could not be found. Make sure you have "
                "deployed before calling this action.").format(self.container)
            return mistral_workflow_utils.Result(error=error)

        try:
            environment = workflow_client.environments.get(self.container)
        except mistralclient_exc.APIException:
            error = "The Mistral environment {} could not be found.".format(
                self.container)
            return mistral_workflow_utils.Result(error=error)

        # We need to check parameter_defaults first for a user provided
        # password. If that doesn't exist, we then should look in the
        # automatically generated passwords.
        # TODO(d0ugal): Abstract this operation somewhere. We shouldn't need to
        # know about the structure of the environment to get a password.
        try:
            parameter_defaults = environment.variables['parameter_defaults']
            passwords = environment.variables['passwords']
            admin_pass = parameter_defaults.get('AdminPassword')
            if admin_pass is None:
                admin_pass = passwords['AdminPassword']
        except KeyError:
            error = ("Unable to find the AdminPassword in the Mistral "
                     "environment.")
            return mistral_workflow_utils.Result(error=error)

        return overcloudrc.create_overcloudrc(stack, self.no_proxy, admin_pass)
