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
import time
import yaml

from heatclient.common import deployment_utils
from heatclient import exc as heat_exc
from mistral_lib import actions
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common.actions import templates
from tripleo_common import constants
from tripleo_common import update
from tripleo_common.utils import overcloudrc
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import swift as swiftutils

LOG = logging.getLogger(__name__)


class OrchestrationDeployAction(base.TripleOAction):

    def __init__(self, server_id, config, name, input_values=[],
                 action='CREATE', signal_transport='TEMP_URL_SIGNAL',
                 timeout=600, group='script'):
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

    def _wait_for_data(self, container_name, object_name, context):
        body = None
        count_check = 0
        swift_client = self.get_object_client(context)
        while not body:
            body = swiftutils.get_object_string(swift_client, container_name,
                                                object_name)
            count_check += 3
            if body or count_check > self.timeout:
                break
            time.sleep(3)

        return body

    def run(self, context):
        heat = self.get_orchestration_client(context)
        swift_client = self.get_object_client(context)

        swift_url = deployment_utils.create_temp_url(swift_client,
                                                     self.name,
                                                     self.timeout / 60)
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

        body = self._wait_for_data(container_name, object_name, context)

        # cleanup
        try:
            sd.delete()
            config.delete()
            swift_client.delete_object(container_name, object_name)
            swift_client.delete_container(container_name)
        except Exception as err:
            LOG.error("Error cleaning up heat deployment resources: %s", err)

        error = None
        if not body:
            body_json = {}
            error = "Timeout for heat deployment '%s'" % self.name
        else:
            body_json = json.loads(body)
            if body_json['deploy_status_code'] != 0:
                error = "Heat deployment failed for '%s'" % self.name

        if error:
            LOG.error(error)

        return actions.Result(data=body_json, error=error)


class DeployStackAction(base.TripleOAction):
    """Deploys a heat stack."""

    def __init__(self, timeout, container=constants.DEFAULT_CONTAINER_NAME,
                 skip_deploy_identifier=False):
        super(DeployStackAction, self).__init__()
        self.container = container
        self.timeout_mins = timeout
        self.skip_deploy_identifier = skip_deploy_identifier
        self.role_data = None

    def run(self, context):
        # check to see if the stack exists
        heat = self.get_orchestration_client(context)
        try:
            stack = heat.stacks.get(self.container, resolve_outputs=False)
        except heat_exc.HTTPNotFound:
            stack = None

        stack_is_new = stack is None

        # update StackAction, DeployIdentifier and UpdateIdentifier
        swift = self.get_object_client(context)

        parameters = dict()
        if not self.skip_deploy_identifier:
            parameters['DeployIdentifier'] = int(time.time())
        else:
            parameters['DeployIdentifier'] = ''
        parameters['UpdateIdentifier'] = ''
        parameters['StackAction'] = 'CREATE' if stack_is_new else 'UPDATE'

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        self.set_tls_parameters(parameters, env)
        try:
            plan_utils.update_in_env(swift, env, 'parameter_defaults',
                                     parameters)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error updating environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        if not stack_is_new:
            try:
                LOG.debug('Checking for compatible neutron mechanism drivers')
                msg = update.check_neutron_mechanism_drivers(env, stack,
                                                             swift,
                                                             self.container)
                if msg:
                    return actions.Result(error=msg)
            except swiftexceptions.ClientException as err:
                err_msg = ("Error getting template %s: %s" % (
                    self.container, err))
                LOG.exception(err_msg)
                return actions.Result(error=err_msg)

        # process all plan files and create or update a stack
        process_templates_action = templates.ProcessTemplatesAction(
            container=self.container
        )
        processed_data = process_templates_action.run(context)
        self.role_data = process_templates_action.role_data

        # If we receive a 'Result' instance it is because the parent action
        # had an error.
        if isinstance(processed_data, actions.Result):
            return processed_data

        # prune roles of unused services after the templates have been
        # processed
        environment = processed_data.get('environment', {})
        resource_reg = environment.get('resource_registry', {})
        roles_changed = self._prune_unused_services(resource_reg, swift)

        if roles_changed:
            # reprocess the data with the new role information
            process_templates_action = templates.ProcessTemplatesAction(
                container=self.container
            )
            processed_data = process_templates_action.run(context)

            # If we receive a 'Result' instance it is because the parent action
            # had an error.
            if isinstance(processed_data, actions.Result):
                return processed_data

        stack_args = processed_data.copy()
        stack_args['timeout_mins'] = self.timeout_mins

        if stack_is_new:
            try:
                swift.copy_object(
                    "%s-swift-rings" % self.container, "swift-rings.tar.gz",
                    "%s-swift-rings/%s-%d" % (
                        self.container, "swift-rings.tar.gz", time.time()))
                swift.delete_object(
                    "%s-swift-rings" % self.container, "swift-rings.tar.gz")
            except swiftexceptions.ClientException:
                pass
            LOG.info("Perfoming Heat stack create")
            try:
                return heat.stacks.create(**stack_args)
            except heat_exc.HTTPException as err:
                err_msg = "Error during stack creation: %s" % (err,)
                LOG.exception(err_msg)
                return actions.Result(error=err_msg)

        LOG.info("Performing Heat stack update")
        stack_args['existing'] = 'true'
        try:
            return heat.stacks.update(stack.id, **stack_args)
        except heat_exc.HTTPException as err:
            err_msg = "Error during stack update: %s" % (err,)
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

    def set_tls_parameters(self, parameters, env,
                           local_ca_path=constants.LOCAL_CACERT_PATH):
        cacert_string = self._get_local_cacert(local_ca_path)
        if cacert_string:
            parameters['CAMap'] = self._get_updated_camap_entry(
                'undercloud-ca', cacert_string, self._get_camap(env))

    def _get_local_cacert(self, local_ca_path):
        # Since the undercloud has TLS by default, we'll add the undercloud's
        # CA to be trusted by the overcloud.
        try:
            with open(local_ca_path, 'rb') as ca_file:
                return ca_file.read().decode('utf-8')
        except IOError:
            # If the file wasn't found it means that the undercloud's TLS
            # was explicitly disabled or another CA is being used. So we'll
            # let the user handle this.
            return None
        except Exception:
            raise

    def _get_camap(self, env):
        return env['parameter_defaults'].get('CAMap', {})

    def _get_updated_camap_entry(self, entry_name, cacert, orig_camap):
        ca_map_entry = {
            entry_name: {
                'content': cacert
            }
        }
        orig_camap.update(ca_map_entry)
        return orig_camap

    def _prune_unused_services(self, resource_registry, swift):
        """Remove unused services from role data

        Finds the unused services in the resource registry and removes them
        from the role data in the plan so we do not create empty service
        chain stacks that are not needed.

        :param resource_registry: tripleo resource registry dict
        :param swift: swift client
        :returns: true if we updated the roles file. else false
        """
        to_remove = set()
        for key, value in resource_registry.items():
            if (key.startswith('OS::TripleO::Services::') and
                    value.startswith('OS::Heat::None')):
                to_remove.add(key)

        if not to_remove or not self.role_data:
            LOG.info('No unused services to prune or no role data')
            return False

        LOG.info('Removing unused services from role data')
        for role in self.role_data:
            role_name = role.get('name')
            for service in to_remove:
                try:
                    role.get('ServicesDefault', []).remove(service)
                    LOG.debug('Removing {} from {} role'.format(
                        service, role_name))
                except ValueError:
                    pass
        LOG.debug('Saving updated role data to swift')
        swift.put_object(self.container,
                         constants.OVERCLOUD_J2_ROLES_NAME,
                         yaml.safe_dump(self.role_data,
                                        default_flow_style=False))
        return True


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

        for cd_exec in workflow_client.executions.list(
                sort_keys="updated_at",
                sort_dirs="desc",
                fields=['input', 'output', 'state'],
                workflow_name='tripleo.deployment.v1.config_download_deploy'
                ):
            if json.loads(cd_exec.input).get('plan_name') == self.plan:
                cd_status = cd_exec.state
                ansible_status = json.loads(
                    cd_exec.output).get('deployment_status')
                break

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


class ConvertStatusAction(base.TripleOAction):
    """Translate a Heat stack status into a config-download deployment status

    """

    def __init__(self, status):
        super(ConvertStatusAction, self).__init__()
        self.status = status

    def run(self, context):
        matrix = {
            'NO_STACK': 'UNDEPLOYED',
            'CREATE_IN_PROGRESS': 'DEPLOYING',
            'CREATE_COMPLETE': 'DEPLOY_SUCCESS',
            'CREATE_FAILED': 'DEPLOY_FAILED',
            'DELETE_COMPLETE': 'UNDEPLOYED',
            'DELETE_IN_PROGRESS': 'UNDEPLOYING',
            'DELETE_FAILED': 'UNDEPLOY_FAILED',
            'UPDATE_IN_PROGRESS': 'DEPLOYING',
            'UPDATE_FAILED': 'DEPLOY_FAILED',
            'UPDATE_COMPLETE': 'DEPLOY_SUCCESS'
        }

        return matrix.get(self.status, 'UNKNOWN')
