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
import subprocess
import time

import passlib.utils as passutils
from tripleo_common import constants


_MIN_PASSWORD_SIZE = 25
LOG = logging.getLogger(__name__)


def generate_overcloud_passwords():
    """Create the passwords needed for the overcloud

    This will create the set of passwords required by the overcloud, store
    them in the output file path and return a dictionary of passwords. If the
    file already exists the existing passwords will be returned instead,
    """

    passwords = {}

    for name in constants.PASSWORD_PARAMETER_NAMES:
        # CephX keys aren't random strings
        if name.startswith("Ceph"):
            passwords[name] = create_cephx_key()
        elif name == 'SnmpdReadonlyUserPassword':
            snmp_password = get_hiera_key(
                'snmpd_readonly_user_password')
            passwords[name] = snmp_password
            if not snmp_password:
                LOG.warning("Undercloud ceilometer SNMPd password "
                            "missing!")
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


def get_hiera_key(key_name):
    """Retrieve a key from the hiera store

    :param password_name: Name of the key to retrieve
    :type  password_name: type
    """

    command = ["hiera", key_name]
    p = subprocess.Popen(command, stdout=subprocess.PIPE)
    out, err = p.communicate()
    return out


def create_keystone_credential():
    return base64.urlsafe_b64encode(os.urandom(32))
