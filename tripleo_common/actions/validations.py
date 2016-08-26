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

from tripleo_common.actions import base
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
