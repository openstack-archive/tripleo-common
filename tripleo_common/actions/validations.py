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

from tripleo_common.actions import base
from tripleo_common.utils import passwords as password_utils


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
