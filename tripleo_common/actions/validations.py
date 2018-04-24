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
from mistral_lib import actions
from mistralclient.api import base as mistralclient_api
from oslo_concurrency.processutils import ProcessExecutionError

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import passwords as password_utils
from tripleo_common.utils import validations as utils


class GetSshKeyAction(base.TripleOAction):

    def run(self, context):
        mc = self.get_workflow_client(context)
        try:
            env = mc.environments.get('ssh_keys')
            p_key = env.variables[self.key_type]
        except Exception:
            ssh_key = password_utils.create_ssh_keypair()
            p_key = ssh_key[self.key_type]

            workflow_env = {
                'name': 'ssh_keys',
                'description': 'SSH keys for TripleO validations',
                'variables': ssh_key
            }
            mc.environments.create(**workflow_env)

        return p_key


class GetPubkeyAction(GetSshKeyAction):

    key_type = 'public_key'


class GetPrivkeyAction(GetSshKeyAction):

    key_type = 'private_key'


class Enabled(base.TripleOAction):
    """Indicate whether the validations have been enabled."""

    def _validations_enabled(self, context):
        """Detect whether the validations are enabled on the undercloud."""
        mistral = self.get_workflow_client(context)
        try:
            # NOTE: the `ssh_keys` environment is created by
            # instack-undercloud only when the validations are enabled on the
            # undercloud (or when they're installed manually). Therefore, we
            # can check for its presence here:
            mistral.environments.get('ssh_keys')
            return True
        except Exception:
            return False

    def run(self, context):
        return_value = {'stderr': ''}
        if self._validations_enabled(context):
            return_value['stdout'] = 'Validations are enabled'
            mistral_result = {"data": return_value}
        else:
            return_value['stdout'] = 'Validations are disabled'
            mistral_result = {"error": return_value}
        return actions.Result(**mistral_result)


class ListValidationsAction(base.TripleOAction):
    """Return a set of TripleO validations"""
    def __init__(self, groups=None):
        super(ListValidationsAction, self).__init__()
        self.groups = groups

    def run(self, context):
        return utils.load_validations(groups=self.groups)


class ListGroupsAction(base.TripleOAction):
    """Return a set of TripleO validation groups"""

    def run(self, context):
        validations = utils.load_validations()
        return {
            group for validation in validations
            for group in validation['groups']
        }


class RunValidationAction(base.TripleOAction):
    """Run the given validation"""
    def __init__(self, validation, plan=constants.DEFAULT_CONTAINER_NAME):
        super(RunValidationAction, self).__init__()
        self.validation = validation
        self.plan = plan

    def run(self, context):
        mc = self.get_workflow_client(context)
        identity_file = None
        try:
            env = mc.environments.get('ssh_keys')
            private_key = env.variables['private_key']
            identity_file = utils.write_identity_file(private_key)

            stdout, stderr = utils.run_validation(self.validation,
                                                  identity_file,
                                                  self.plan,
                                                  context)
            return_value = {'stdout': stdout, 'stderr': stderr}
            mistral_result = {"data": return_value}
        except mistralclient_api.APIException as e:
            return_value = {'stdout': '', 'stderr': e.error_message}
            mistral_result = {"error": return_value}
        except ProcessExecutionError as e:
            return_value = {'stdout': e.stdout, 'stderr': e.stderr}
            # Indicates to Mistral there was a failure
            mistral_result = {"error": return_value}
        finally:
            if identity_file:
                utils.cleanup_identity_file(identity_file)
        return actions.Result(**mistral_result)


class UploadValidationsAction(base.UploadDirectoryAction):
    """Upload default validations for TripleO."""
    def __init__(self, container=constants.VALIDATIONS_CONTAINER_NAME,
                 dir_to_upload=constants.DEFAULT_VALIDATIONS_PATH):
        super(UploadValidationsAction, self).__init__(container, dir_to_upload)
