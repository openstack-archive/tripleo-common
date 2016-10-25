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
import base64
import logging
import os
import struct
import time
import uuid

import passlib.utils as passutils
import six

from tripleo_common import constants


_MIN_PASSWORD_SIZE = 25
LOG = logging.getLogger(__name__)


def generate_overcloud_passwords(mistralclient, stack_env=None):
    """Create the passwords needed for the overcloud

    This will create the set of passwords required by the overcloud, store
    them in the output file path and return a dictionary of passwords.
    """

    passwords = {}

    for name in constants.PASSWORD_PARAMETER_NAMES:

        # Support users upgrading from Mitaka or otherwise creating a plan for
        # a Heat stack that already exists.
        if stack_env and name in stack_env.get('parameter_defaults', {}):
            passwords[name] = stack_env['parameter_defaults'][name]
        elif name.startswith("Ceph"):
            if name == "CephClusterFSID":
                # The FSID must be a UUID
                passwords[name] = six.text_type(uuid.uuid1())
            else:
                # CephX keys aren't random strings
                passwords[name] = create_cephx_key()
        # The SnmpdReadonlyUserPassword is stored in a mistral env.
        elif name == 'SnmpdReadonlyUserPassword':
            passwords[name] = get_snmpd_readonly_user_password(mistralclient)
        elif name in ('KeystoneCredential0', 'KeystoneCredential1'):
            passwords[name] = create_keystone_credential()
        else:
            passwords[name] = passutils.generate_password(
                size=_MIN_PASSWORD_SIZE)
    return passwords


def create_cephx_key():
    # NOTE(gfidente): Taken from
    # https://github.com/ceph/ceph-deploy/blob/master/ceph_deploy/new.py#L21
    key = os.urandom(16)
    header = struct.pack("<hiih", 1, int(time.time()), 0, len(key))
    return base64.b64encode(header + key)


def get_snmpd_readonly_user_password(mistralclient):
    mistral_env = mistralclient.environments.get("tripleo.undercloud-config")
    try:
        return mistral_env.variables['undercloud_ceilometer_snmpd_password']
    except KeyError:
        LOG.error("Undercloud ceilometer SNMPd password missing!")
        raise


def create_keystone_credential():
    return base64.urlsafe_b64encode(os.urandom(32))
