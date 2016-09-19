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
import os
import shutil
import tempfile

from mistral.workflow import utils as mistral_workflow_utils
from mistralclient.api import base as mistralclient_api
from oslo_concurrency.processutils import ProcessExecutionError

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import validations as utils


class GetPubkeyAction(base.TripleOAction):
    def __init__(self):
        super(GetPubkeyAction, self).__init__()

    def run(self):
        mc = self._get_workflow_client()
        try:
            env = mc.environments.get('ssh_keys')
            public_key = env.variables['public_key']
        except Exception:
            tmp_dir = tempfile.mkdtemp()
            private_key_path = os.path.join(tmp_dir, 'id_rsa')
            public_key_path = private_key_path + '.pub'
            utils.create_ssh_keypair(private_key_path)

            with open(private_key_path, 'r') as f:
                private_key = f.read().strip()
            with open(public_key_path, 'r') as f:
                public_key = f.read().strip()

            shutil.rmtree(tmp_dir)

            workflow_env = {
                'name': 'ssh_keys',
                'description': 'SSH keys for TripleO validations',
                'variables': {
                    'public_key': public_key,
                    'private_key': private_key,
                }
            }
            mc.environments.create(**workflow_env)

        return public_key


class Enabled(base.TripleOAction):
    """Indicate whether the validations have been enabled."""

    def __init__(self):
        super(Enabled, self).__init__()

    def _validations_enabled(self):
        """Detect whether the validations are enabled on the undercloud."""
        mistral = self._get_workflow_client()
        try:
            # NOTE: the `ssh_keys` environment is created by
            # instack-undercloud only when the validations are enabled on the
            # undercloud (or when they're installed manually). Therefore, we
            # can check for its presence here:
            mistral.environments.get('ssh_keys')
            return True
        except Exception:
            return False

    def run(self):
        return_value = {'stderr': ''}
        if self._validations_enabled():
            return_value['stdout'] = 'Validations are enabled'
            mistral_result = (return_value, None)
        else:
            return_value['stdout'] = 'Validations are disabled'
            mistral_result = (None, return_value)
        return mistral_workflow_utils.Result(*mistral_result)


class ListValidationsAction(base.TripleOAction):
    """Return a set of TripleO validations"""
    def __init__(self, groups=None):
        super(ListValidationsAction, self).__init__()
        self.groups = groups

    def run(self):
        return utils.load_validations(groups=self.groups)


class ListGroupsAction(base.TripleOAction):
    """Return a set of TripleO validation groups"""
    def __init__(self):
        super(ListGroupsAction, self).__init__()

    def run(self):
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

    def run(self):
        mc = self._get_workflow_client()
        identity_file = None
        try:
            env = mc.environments.get('ssh_keys')
            private_key = env.variables['private_key']
            identity_file = utils.write_identity_file(private_key)

            stdout, stderr = utils.run_validation(self.validation,
                                                  identity_file,
                                                  self.plan)
            return_value = {'stdout': stdout, 'stderr': stderr}
            mistral_result = (return_value, None)
        except mistralclient_api.APIException as e:
            return_value = {'stdout': '', 'stderr': e.error_message}
            mistral_result = (None, return_value)
        except ProcessExecutionError as e:
            return_value = {'stdout': e.stdout, 'stderr': e.stderr}
            # Indicates to Mistral there was a failure
            mistral_result = (None, return_value)
        finally:
            if identity_file:
                utils.cleanup_identity_file(identity_file)
        return mistral_workflow_utils.Result(*mistral_result)
