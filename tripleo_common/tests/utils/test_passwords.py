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
import sys
from unittest import mock

from oslo_utils import uuidutils

from tripleo_common.tests import base
from tripleo_common.utils import passwords as password_utils


class TestPasswords(base.TestCase):

    def setUp(self):
        super(TestPasswords, self).setUp()

        if (sys.version_info > (3, 0)):
            self.open_builtins = 'builtins.open'
        else:
            self.open_builtins = '__builtin__.open'

        self.snmp_test_pw = '78cbc32b858718267c355d4'

    def test_create_cephx_key(self):
        key = password_utils.create_cephx_key()
        self.assertEqual(len(key), 40)

    def test_get_snmpd_readonly_user_password(self):
        with mock.patch(self.open_builtins, mock.mock_open(read_data="data")):
            with mock.patch('yaml.safe_load') as mock_yaml:
                with mock.patch('os.path.exists') as mock_exists:
                    mock_exists.return_value = True
                    mock_yaml.return_value = {
                        'parameter_defaults': {
                            'SnmpdReadonlyUserPassword': self.snmp_test_pw
                        }
                    }
                    value = password_utils.get_snmpd_readonly_user_password()

        self.assertEqual(value, self.snmp_test_pw)

    @mock.patch('tripleo_common.utils.passwords.create_keystone_credential')
    def test_fernet_keys_and_credentials(self, mock_create_creds):

        keys = [uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False)]

        # generate_passwords will be called multiple times
        # but the order is based on how the strings are hashed, and thus
        # not really predictable. So, make sure it is a unique one of the
        # generated values

        mock_create_creds.side_effect = keys
        with mock.patch(self.open_builtins, mock.mock_open(read_data="data")):
            with mock.patch('yaml.load') as mock_yaml:
                mock_yaml.return_value = {
                    'parameter_defaults': {
                        'SnmpdReadonlyUserPassword': self.snmp_test_pw
                    }
                }
                value = password_utils.generate_passwords()
        self.assertIn(value['KeystoneCredential0'], keys)
        self.assertIn(value['KeystoneCredential1'], keys)
        self.assertIn(value['KeystoneFernetKey0'], keys)
        self.assertIn(value['KeystoneFernetKey1'], keys)
        self.assertIn(value['BarbicanSimpleCryptoKek'], keys)

        self.assertNotEqual(value['KeystoneFernetKey0'],
                            value['KeystoneFernetKey1'])

        self.assertNotEqual(value['KeystoneCredential0'],
                            value['KeystoneCredential1'])
        self.assertEqual(len(value['OctaviaServerCertsKeyPassphrase']), 32)

    def test_create_ssh_keypair(self):

        value = password_utils.create_ssh_keypair(comment="Foo")
        self.assertEqual('ssh-rsa', value['public_key'][:7])
        self.assertEqual('Foo', value['public_key'][-3:])
