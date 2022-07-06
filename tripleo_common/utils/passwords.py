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
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend
import hashlib
import hmac
import logging
import os
import struct
import time
import uuid
import urllib.parse

import passlib.pwd
import yaml

from tripleo_common import constants


_MIN_PASSWORD_SIZE = 25
KEYSTONE_FERNET_REPO = '/etc/keystone/fernet-keys/'
LOG = logging.getLogger(__name__)


def generate_passwords(stack_env=None,
                       rotate_passwords=False,
                       rotate_pw_list=None):
    """Create the passwords needed for deploying OpenStack via t-h-t.

    This will create the set of passwords required by the undercloud and
    overcloud installers that use tripleo-heat-templates and return them
    as a dict.
    """

    if not stack_env:
        stack_env = {}
    passwords = {}
    db_ed25519 = stack_env.get('parameter_defaults', {}) \
                          .get('EnableMysqlAuthEd25519', False)
    if db_ed25519:
        passwords['EnableMysqlAuthEd25519'] = True
    for name in constants.PASSWORD_PARAMETER_NAMES:
        no_rotate = (not rotate_passwords or (
            rotate_pw_list and name not in rotate_pw_list)
            or name in constants.DO_NOT_ROTATE_LIST)
        if no_rotate and (
            stack_env and name in stack_env.get(
                'parameter_defaults', {})):
            current_password = stack_env['parameter_defaults'][name]
            passwords[name] = current_password
            if name in constants.DB_PASSWORD_PARAMETER_NAMES and db_ed25519:
                db_uri = db_uri_from_ed25519_password(current_password)
                passwords[name + 'Database'] = db_uri
        elif (name == 'KeystonePassword' and stack_env and
                'AdminToken' in stack_env.get('parameter_defaults', {})):
            # NOTE(tkajinam): AdminToken was renamed to KeystonePassword
            passwords[name] = stack_env['parameter_defaults']['AdminToken']
        elif name in ('CephClientKey', 'CephManilaClientKey', 'CephRgwKey'):
            # CephX keys aren't random strings
            passwords[name] = create_cephx_key()
        elif name == "CephClusterFSID":
            # The FSID must be a UUID
            passwords[name] = str(uuid.uuid4())
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
        elif name in ('KeystoneCredential0', 'KeystoneCredential1'):
            passwords[name] = create_keystone_credential()
        elif name == 'KeystoneFernetKeys':
            passwords[name] = create_fernet_keys_repo_structure_and_keys()
        elif name == 'MigrationSshKey':
            passwords[name] = create_ssh_keypair()
        elif name == 'BarbicanSimpleCryptoKek':
            passwords[name] = create_keystone_credential()
        elif name in constants.DB_PASSWORD_PARAMETER_NAMES and db_ed25519:
            # root and clustercheck passwords can't contain a null
            # byte due to a mariadb limitation in config file
            # TODO: bytes used as word separators can't be used either
            # as long as password is used as a shell parameter
            if name == 'MysqlRootPassword' or \
               name == 'MysqlClustercheckPassword':
                skip_bytes = [0, ord(' '), ord('\t'), ord('\n')]
                passwords[name] = create_ed25519_password(skip_bytes)
            else:
                ed25519_password = create_ed25519_password()
                db_uri = db_uri_from_ed25519_password(ed25519_password)
                passwords[name] = ed25519_password
                passwords[name + 'Database'] = db_uri
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

    with open(pw_file) as f:
        passwords = yaml.safe_load(f.read())

    return passwords['parameter_defaults']['SnmpdReadonlyUserPassword']


def create_keystone_credential():
    return base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8')


def create_ssh_keypair(comment=None, bits=2048):
    """Generate an ssh keypair for use on the overcloud"""
    if comment is None:
        comment = "Generated by TripleO"
    key = rsa.generate_private_key(public_exponent=65537,
                                   key_size=bits,
                                   backend=default_backend())
    private_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode('utf-8')
    public_key = key.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH).decode('utf-8')
    public_key = '{} {}'.format(public_key, comment)
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


def create_ed25519_password(skip_bytes=[]):
    generate_new_key = True
    while generate_new_key:
        private_key = ed25519.Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption()
        )
        generate_new_key = any(x in skip_bytes for x in private_bytes)
    return base64.b64encode(private_bytes).decode('utf-8')


def db_uri_from_ed25519_password(b64_password):
    decoded = base64.b64decode(b64_password).decode("latin-1")
    # A database URI is unquoted by oslo.db as per RFC 1738,
    # but we also need to quote '/' because that is a valid
    # character in ed25519 passwords
    db_uri = urllib.parse.quote(decoded.encode("utf-8")).replace('/', '%2F')
    return db_uri
