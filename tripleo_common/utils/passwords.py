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
import hashlib
import hmac
import logging
import os
import paramiko
import struct
import time
import uuid

import passlib.pwd
import six
import yaml

from tripleo_common import constants


_MIN_PASSWORD_SIZE = 25
KEYSTONE_FERNET_REPO = '/etc/keystone/fernet-keys/'
LOG = logging.getLogger(__name__)


def generate_passwords(stack_env=None,
                       rotate_passwords=False):
    """Create the passwords needed for deploying OpenStack via t-h-t.

    This will create the set of passwords required by the undercloud and
    overcloud installers that use tripleo-heat-templates and return them
    as a dict.
    """

    passwords = {}

    for name in constants.PASSWORD_PARAMETER_NAMES:
        # Support users upgrading from Mitaka or otherwise creating a plan for
        # a Heat stack that already exists.
        if (stack_env and name in stack_env.get('parameter_defaults', {}) and
                not rotate_passwords):
            passwords[name] = stack_env['parameter_defaults'][name]
        elif name in ('CephClientKey', 'CephManilaClientKey', 'CephRgwKey'):
            # CephX keys aren't random strings
            passwords[name] = create_cephx_key()
        elif name == "CephClusterFSID":
            # The FSID must be a UUID
            passwords[name] = six.text_type(uuid.uuid4())
        # Since by default passlib.pwd.genword uses all digits and ascii upper
        # & lowercase letters, it provides ~5.95 entropy per character.
        # Make the length of the default authkey 4096 bytes, which should give
        # us ~24000 bits of randomness
        elif name.startswith("PacemakerRemoteAuthkey"):
            passwords[name] = passlib.pwd.genword(
                length=4096)
        # The underclouds SnmpdReadonlyUserPassword is stored in a mistral env
        # for the overcloud.
        elif name == 'SnmpdReadonlyUserPassword':
            passwords[name] = get_snmpd_readonly_user_password()
        elif name in ('KeystoneCredential0', 'KeystoneCredential1',
                      'KeystoneFernetKey0', 'KeystoneFernetKey1'):
            passwords[name] = create_keystone_credential()
        elif name == 'KeystoneFernetKeys':
            passwords[name] = create_fernet_keys_repo_structure_and_keys()
        elif name == 'MigrationSshKey':
            passwords[name] = create_ssh_keypair()
        elif name == 'BarbicanSimpleCryptoKek':
            passwords[name] = create_keystone_credential()
        elif name.startswith("MysqlRootPassword"):
            passwords[name] = passlib.pwd.genword(length=10)
        elif name.startswith("RabbitCookie"):
            passwords[name] = passlib.pwd.genword(length=20)
        elif name.startswith("PcsdPassword"):
            passwords[name] = passlib.pwd.genword(length=16)
        elif name.startswith("HorizonSecret"):
            passwords[name] = passlib.pwd.genword(length=10)
        elif name.startswith("HeatAuthEncryptionKey"):
            passwords[name] = passlib.pwd.genword(length=32)
        elif name.startswith("OctaviaServerCertsKeyPassphrase"):
            passwords[name] = passlib.pwd.genword(length=32)
        elif name.startswith("DesignateRndcKey"):
            passwords[name] = create_rndc_key_secret()
        else:
            passwords[name] = passlib.pwd.genword(length=_MIN_PASSWORD_SIZE)
    return passwords


def create_fernet_keys_repo_structure_and_keys():
    return {
        KEYSTONE_FERNET_REPO + '0': {
            'content': create_keystone_credential()},
        KEYSTONE_FERNET_REPO + '1': {
            'content': create_keystone_credential()}
    }


def create_cephx_key():
    # NOTE(gfidente): Taken from
    # https://github.com/ceph/ceph-deploy/blob/master/ceph_deploy/new.py#L21
    key = os.urandom(16)
    header = struct.pack("<hiih", 1, int(time.time()), 0, len(key))
    return base64.b64encode(header + key).decode('utf-8')


def get_snmpd_readonly_user_password(pw_file=None):
    """Return mistral password from a given yaml file.

    :param pw_file: Full path to a given password file. If no file is defined
                    the file used will be ~/tripleo-undercloud-passwords.yaml.
    :type pw_file: String

    :returns: String
    """

    if not pw_file:
        home = os.path.expanduser('~' + os.environ.get('SUDO_USER', ''))
        pw_file = os.path.expanduser(
            os.path.join(
                home,
                'tripleo-undercloud-passwords.yaml'
            )
        )

    if not os.path.exists(pw_file):
        return passlib.pwd.genword(length=24)
    else:
        with open(pw_file) as f:
            passwords = yaml.safe_load(f.read())

        return passwords['parameter_defaults']['SnmpdReadonlyUserPassword']


def create_keystone_credential():
    return base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8')


def create_ssh_keypair(comment=None, bits=2048):
    """Generate an ssh keypair for use on the overcloud"""
    if comment is None:
        comment = "Generated by TripleO"
    key = paramiko.RSAKey.generate(bits)
    keyout = six.StringIO()
    key.write_private_key(keyout)
    private_key = keyout.getvalue()
    public_key = '{} {} {}'.format(key.get_name(), key.get_base64(), comment)
    return {
        'private_key': private_key,
        'public_key': public_key,
    }


def create_rndc_key_secret():
    # The rndc key secret is a base64-encoded hmac-sha256 value
    h = hmac.new(
        passlib.pwd.genword(length=_MIN_PASSWORD_SIZE).encode('utf-8'),
        msg=passlib.pwd.genword(length=_MIN_PASSWORD_SIZE).encode('utf-8'),
        digestmod=hashlib.sha256)
    return base64.b64encode(h.digest()).decode('utf-8')
