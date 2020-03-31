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
import os
import yaml

from heatclient import exc as heat_exc
from mistral_lib import actions
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import overcloudrc
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import swift as swiftutils

LOG = logging.getLogger(__name__)


class OvercloudRcAction(base.TripleOAction):
    """Generate the overcloudrc for a plan

    Given the name of a container, generate the overcloudrc files needed to
    access the overcloud via the CLI.

    no_proxy is optional and is a comma-separated string of hosts that
    shouldn't be proxied
    """

    def __init__(self, container, no_proxy=""):
        super(OvercloudRcAction, self).__init__()
        self.container = container
        self.no_proxy = no_proxy

    def run(self, context):
        orchestration_client = self.get_orchestration_client(context)
        swift = self.get_object_client(context)

        try:
            stack = orchestration_client.stacks.get(self.container)
        except heat_exc.HTTPNotFound:
            error = (
                "The Heat stack {} could not be found. Make sure you have "
                "deployed before calling this action.").format(self.container)
            return actions.Result(error=error)

        # We need to check parameter_defaults first for a user provided
        # password. If that doesn't exist, we then should look in the
        # automatically generated passwords.
        # TODO(d0ugal): Abstract this operation somewhere. We shouldn't need to
        # know about the structure of the environment to get a password.
        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.error(err_msg)
            return actions.Result(error=err_msg)

        try:
            parameter_defaults = env['parameter_defaults']
            passwords = env['passwords']
            admin_pass = parameter_defaults.get('AdminPassword')
            if admin_pass is None:
                admin_pass = passwords['AdminPassword']
        except KeyError:
            error = ("Unable to find the AdminPassword in the plan "
                     "environment.")
            return actions.Result(error=error)

        region_name = parameter_defaults.get('KeystoneRegion')
        return overcloudrc.create_overcloudrc(stack, self.no_proxy, admin_pass,
                                              region_name)


class DeploymentFailuresAction(base.TripleOAction):
    """Return all of the failures (if any) from deploying the plan

    :param plan: name of the Swift container / plan name
    """

    def __init__(self,
                 plan=constants.DEFAULT_CONTAINER_NAME,
                 work_dir=constants.MISTRAL_WORK_DIR,
                 ansible_errors_file=constants.ANSIBLE_ERRORS_FILE):
        super(DeploymentFailuresAction, self).__init__()
        self.plan = plan
        self.work_dir = work_dir
        self.ansible_errors_file = ansible_errors_file

    def _format_return(self, message, failures={}):
        return dict(message=message,
                    failures=failures)

    def run(self, context):
        try:
            failures_file = os.path.join(self.work_dir, self.plan,
                                         self.ansible_errors_file)
            failures = json.loads(open(failures_file).read())
            return self._format_return('', failures)
        except IOError:
            return self._format_return(
                'Ansible errors file not found at %s' % failures_file)


class DeploymentStatusAction(base.TripleOAction):
    """Get the deployment status and update it if necessary

    The status will be set based off of the stack status and any running
    config_download workflow.
    """

    def __init__(self,
                 plan=constants.DEFAULT_CONTAINER_NAME):
        super(DeploymentStatusAction, self).__init__()
        self.plan = plan

    def run(self, context):
        orchestration_client = self.get_orchestration_client(context)
        workflow_client = self.get_workflow_client(context)
        swift_client = self.get_object_client(context)

        try:
            stack = orchestration_client.stacks.get(self.plan)
        except heat_exc.HTTPNotFound:
            return dict(status_update=None,
                        deployment_status=None)

        try:
            body = swiftutils.get_object_string(swift_client,
                                                '%s-messages' % self.plan,
                                                'deployment_status.yaml')

            deployment_status = yaml.safe_load(body)['deployment_status']
        except swiftexceptions.ClientException:
            deployment_status = None

        stack_status = stack.stack_status
        cd_status = None
        ansible_status = None
        # Will get set to new status if an update is required
        status_update = None

        cd_execs = workflow_client.executions.find(
            workflow_name='tripleo.deployment.v1.config_download_deploy')
        cd_execs.sort(key=lambda x: x.updated_at)
        if cd_execs:
            cd_exec = workflow_client.executions.get(cd_execs[-1].id)
            cd_status = cd_exec.state
            ansible_status = json.loads(
                cd_exec.output).get('deployment_status')

        def update_status(status):
            # If we need to update the status return it
            if deployment_status != status:
                return status

        # Update the status if needed. We do this since tripleoclient does not
        # yet use a single API for overcloud deployment. Since there is no long
        # running process to make sure the status is updated, we instead update
        # the status if needed when we get it with this action.
        #
        # The logic here is:
        #
        # If stack or config_download is in progress, then the status is
        # deploying.
        #
        # Else if stack is failed or config_download is failed or ansible is
        # failed, then the status is failed.
        #
        # Else if config_download status is success and ansible is success
        # then status is success.
        #
        # Else, we just return the read deployment_status from earlier.
        if stack_status.endswith('IN_PROGRESS') or cd_status == 'RUNNING':
            status_update = update_status('DEPLOYING')
        elif stack_status.endswith('FAILED') or cd_status == 'FAILED' \
                or ansible_status == 'DEPLOY_FAILED':
            status_update = update_status('DEPLOY_FAILED')
        elif cd_status == 'SUCCESS' and ansible_status == 'DEPLOY_SUCCESS':
            status_update = update_status('DEPLOY_SUCCESS')

        return dict(cd_status=cd_status,
                    stack_status=stack_status,
                    deployment_status=deployment_status,
                    ansible_status=ansible_status,
                    status_update=status_update)
