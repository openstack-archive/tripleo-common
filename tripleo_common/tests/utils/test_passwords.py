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
import mock

from oslo_utils import uuidutils

from tripleo_common.tests import base
from tripleo_common.utils import passwords as password_utils


class TestPasswords(base.TestCase):

    def test_create_cephx_key(self):
        key = password_utils.create_cephx_key()
        self.assertEqual(len(key), 40)

    def test_get_snmpd_readonly_user_password(self):

        mock_mistral = mock.Mock()
        mock_mistral.environments.get.return_value = mock.Mock(variables={
            "undercloud_ceilometer_snmpd_password": "78cbc32b858718267c355d4"
        })

        value = password_utils.get_snmpd_readonly_user_password(mock_mistral)

        self.assertEqual(value, "78cbc32b858718267c355d4")

    @mock.patch('tripleo_common.utils.passwords.create_keystone_credential')
    def test_fernet_keys_and_credentials(self, mock_create_creds):

        keys = [uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False),
                uuidutils.generate_uuid(dashed=False)]

        snmpd_password = uuidutils.generate_uuid(dashed=False)

        mock_mistral = mock.Mock()
        mock_mistral.environments.get.return_value = mock.Mock(variables={
            "undercloud_ceilometer_snmpd_password": snmpd_password
        })

        # generate_passwords will be called multiple times
        # but the order is based on how the strings are hashed, and thus
        # not really predictable. So, make sure it is a unique one of the
        # generated values

        mock_create_creds.side_effect = keys
        value = password_utils.generate_passwords(mock_mistral)
        self.assertIn(value['KeystoneCredential0'], keys)
        self.assertIn(value['KeystoneCredential1'], keys)
        self.assertIn(value['KeystoneFernetKey0'], keys)
        self.assertIn(value['KeystoneFernetKey1'], keys)

        self.assertNotEqual(value['KeystoneFernetKey0'],
                            value['KeystoneFernetKey1'])

        self.assertNotEqual(value['KeystoneCredential0'],
                            value['KeystoneCredential1'])

    def test_create_ssh_keypair(self):

        value = password_utils.create_ssh_keypair(comment="Foo")
        self.assertEqual('ssh-rsa', value['public_key'][:7])
        self.assertEqual('Foo', value['public_key'][-3:])
