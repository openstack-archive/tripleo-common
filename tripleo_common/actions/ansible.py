# Copyright 2017 Red Hat, Inc.
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

from tripleo_common.utils import ansible as ansible_utils


# FIXME(ramishra) Left behind till we've a new tripleo-common release
def write_default_ansible_cfg(work_dir,
                              remote_user,
                              ssh_private_key=None,
                              transport=None,
                              base_ansible_cfg='/etc/ansible/ansible.cfg',
                              override_ansible_cfg=None):

    return ansible_utils.write_default_ansible_cfg(
        work_dir, remote_user,
        ssh_private_key, transport,
        base_ansible_cfg,
        override_ansible_cfg)
