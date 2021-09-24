# Copyright (c) 2017 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest import mock

from tripleo_common import constants
from tripleo_common.tests import base
from tripleo_common.utils import passwords as password_utils
from tripleo_common.utils import plan as plan_utils


PLAN_ENV_CONTENTS = """
version: 1.0

name: overcloud
template: overcloud.yaml
environments:
-  path: overcloud-resource-registry-puppet.yaml
-  path: environments/services/sahara.yaml
parameter_defaults:
  BlockStorageCount: 42
  OvercloudControlFlavor: yummy
passwords:
  AdminPassword: aaaa
"""

USER_ENV_CONTENTS = """
resource_registry:
  OS::TripleO::Foo: bar.yaml
"""

UNORDERED_PLAN_ENV_LIST = [
    {'path': 'overcloud-resource-registry-puppet.yaml'},
    {'path': 'environments/docker-ha.yaml'},
    {'path': 'environments/custom-environment-not-in-capabilities-map.yaml'},
    {'path': 'environments/containers-default-parameters.yaml'},
    {'path': 'environments/docker.yaml'}
]

CAPABILITIES_DICT = {
    'topics': [{
        'environment_groups': [{
            'environments': [{
                'file': 'overcloud-resource-registry-puppet.yaml'}
            ]}, {
            'environments': [{
                'file': 'environments/docker.yaml',
                'requires': ['overcloud-resource-registry-puppet.yaml']
            }, {
                'file': 'environments/containers-default-parameters.yaml',
                'requires': ['overcloud-resource-registry-puppet.yaml',
                             'environments/docker.yaml']
            }]}, {
            'environments': [{
                'file': 'environments/docker-ha.yaml',
                'requires': ['overcloud-resource-registry-puppet.yaml',
                             'environments/docker.yaml']
            }]}
        ]
    }]
}

_EXISTING_PASSWORDS = {
    'PlacementPassword': 'VFJeqBKbatYhQm9jja67hufft',
    'BarbicanPassword': 'MGGQBtgKT7FnywvkcdMwE9nhx',
    'BarbicanSimpleCryptoKek': 'dGhpcnR5X3R3b19ieXRlX2tleWJsYWhibGFoYmxhaGg=',
    'AdminPassword': 'jFmY8FTpvtF2e4d4ReXvmUP8k',
    'CeilometerMeteringSecret': 'CbHTGK4md4Cc8P8ZyzTns6wry',
    'NovaPassword': '7dZATgVPwD7Ergs9kTTDMCr7F',
    'MysqlRootPassword': 'VqJYpEdKks',
    'RabbitCookie': 'BqJYpEdKksAqJYpEdKks',
    'HeatAuthEncryptionKey': '9xZXehsKc2HbmFFMKjuqxTJHn',
    'PcsdPassword': 'KjEzeitus8eu751a',
    'HorizonSecret': 'mjEzeitus8eu751B',
    'NovajoinPassword': '7dZATgVPwD7Ergs9kTTDMCr7F',
    'IronicPassword': '4hFDgn9ANeVfuqk84pHpD4ksa',
    'RedisPassword': 'xjj3QZDcUQmU6Q7NzWBHRUhGd',
    'CinderPassword': 'dcxC3xyUcrmvzfrrxpAd3REcm',
    'GlancePassword': 'VqJYNEdKKsGZtgnHct77XBtrV',
    'RabbitPassword': 'ahuHRXdPMx9rzCdjD9CJJNCgA',
    'RpcPassword': 'ahuHRXdPMx9rzCdjD9CJJNCgA',
    'NotifyPassword': 'ahuHRXdPMx9rzCdjD9CJJNCgA',
    'HAProxyStatsPassword': 'P8tbdK6n4YUkTaUyy8XgEVTe6',
    'CeilometerPassword': 'RRdpwK6qf2pbKz2UtzxqauAdk',
    'GnocchiPassword': 'cRYHcUkMuJeK3vyU9pCaznUZc',
    'HeatStackDomainAdminPassword': 'GgTRyWzKYsxK4mReTJ4CM6sMc',
    'CephRgwKey': b'AQCQXtlXAAAAABAAUKcqUMu6oMjAXMjoUV4/3A==',
    'AodhPassword': '8VZXehsKc2HbmFFMKYuqxTJHn',
    'OctaviaHeartbeatKey': 'oct-heartbeat-key',
    'OctaviaPassword': 'NMl7j3nKk1VVwMxUZC8Cgw==',
    'OctaviaServerCertsKeyPassphrase': 'aW5zZWN1cmUta2V5LWRvLW5vdC11c2U=',
    'OctaviaCaKeyPassphrase': 'SLj4c3uCk4DDxPwQOG1Heb==',
    'ManilaPassword': 'NYJN86Fua3X8AVFWmMhQa2zTH',
    'NeutronMetadataProxySharedSecret': 'Q2YgUCwmBkYdqsdhhCF4hbghu',
    'CephManilaClientKey': b'AQANOFFY1NW6AxAAu6jWI3YSOsp2QWusb5Y3DQ==',
    'CephGrafanaAdminPassword': 'NYJN86Fua3X8AVFWmMhQa2zTH',
    'CephDashboardAdminPassword': 'NYJN86Fua3X8AVFWmMhQa2zTH',
    'SwiftHashSuffix': 'td8mV6k7TYEGKCDvjVBwckpn9',
    'SnmpdReadonlyUserPassword': 'TestPassword',
    'SwiftPassword': 'z6EWAVfW7CuxvKdzjWTdrXCeg',
    'HeatPassword': 'bREnsXtMHKTHxt8XW6NXAYr48',
    'MysqlClustercheckPassword': 'jN4RMMWWJ4sycaRwh7UvrAtfX',
    'CephClientKey': b'AQCQXtlXAAAAABAAKyc+8St8i9onHyu2mPk+vg==',
    'NeutronPassword': 'ZxAjdU2UXCV4GM3WyPKrzAZXD',
    'DesignatePassword': 'wHYj7rftFzHMpJKnGxbjjR9CW',
    'DesignateRndcKey': 'hB8XaZRd2Tf00jKsyoXpyw==',
    'KeystoneCredential0': 'ftJNQ_XlDUK7Lgvv1kdWf3SyqVsrvNDgoNV4kJg3yzw=',
    'KeystoneCredential1': 'c4MFq82TQLFLKpiiUjrKkp15dafE2ALcD3jbaIu3rfE=',
    'KeystoneFernetKey0': 'O8NSPxr4zXBBAoGIj-5aUmtE7-Jk5a4ptVsEhzJ8Vd8=',
    'KeystoneFernetKey1': 'AueoL37kd6eLjV29AG-Ruxu5szW47osgXx6aPOqtI6I=',
    'KeystoneFernetKeys': {
        '/etc/keystone/fernet-keys/0': {'content': 'IAMAVERYSAFEKEY'},
        '/etc/keystone/fernet-keys/1': {'content': 'IALSOAMAVERYSAFEKEY'}
    },
    'KeystonePassword': 'jq6G6HyZtj7dcZEvuyhAfjutM',
    'CephClusterFSID': u'97c16f44-b62c-11e6-aed3-185e0f73fdc5',
    'EtcdInitialClusterToken': 'fcVZXehsSc2KdmFFMKDudxTLKa',
    'PacemakerRemoteAuthkey':
        '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'
        'sGhUtCQVed7dtj12',
    'MigrationSshKey': {
        'private_key': 'private_key',
        'public_key': 'public_key'
        },
    'LibvirtTLSPassword': 'xCdt9yeamKz8Fb6EGba9u82XU',
}


class PlanTest(base.TestCase):
    def setUp(self):
        super(PlanTest, self).setUp()
        self.container = 'overcloud'

    def test_get_next_index(self):
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'Some key'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'Some other key'},
        }
        next_index = plan_utils.get_next_index(keys_map)
        self.assertEqual(next_index, 2)

    @mock.patch('tripleo_common.utils.passwords.'
                'create_keystone_credential')
    def test_rotate_keys(self, mock_keystone_creds):
        mock_keystone_creds.return_value = 'Some new key'

        staged_key_index = password_utils.KEYSTONE_FERNET_REPO + '0'
        new_primary_key_index = password_utils.KEYSTONE_FERNET_REPO + '2'
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'Some key'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'Some other key'},
        }
        new_keys_map = plan_utils.rotate_keys(keys_map, 2)

        # Staged key should be the new key
        self.assertEqual('Some new key',
                         new_keys_map[staged_key_index]['content'])
        # primary key should be the previous staged key
        self.assertEqual('Some key',
                         new_keys_map[new_primary_key_index]['content'])

    def test_purge_excess_keys_should_purge(self):
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'key0'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'key1'},
            password_utils.KEYSTONE_FERNET_REPO + '2': {
                'content': 'key2'},
            password_utils.KEYSTONE_FERNET_REPO + '3': {
                'content': 'key3'},
            password_utils.KEYSTONE_FERNET_REPO + '4': {
                'content': 'key4'},
        }
        max_keys = 3
        keys_map = plan_utils.purge_excess_keys(max_keys, keys_map)
        self.assertEqual(max_keys, len(keys_map))
        # It should keep index 0, 3 and 4
        self.assertIn(password_utils.KEYSTONE_FERNET_REPO + '0', keys_map)
        self.assertIn(password_utils.KEYSTONE_FERNET_REPO + '3', keys_map)
        self.assertIn(password_utils.KEYSTONE_FERNET_REPO + '4', keys_map)
        # It sould have removed index 1 and 2
        self.assertNotIn(password_utils.KEYSTONE_FERNET_REPO + '1', keys_map)
        self.assertNotIn(password_utils.KEYSTONE_FERNET_REPO + '2', keys_map)

    def test_purge_excess_keys_should_not_purge_if_equal_to_max(self):
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'key0'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'key1'},
            password_utils.KEYSTONE_FERNET_REPO + '2': {
                'content': 'key2'},
        }
        max_keys = 3
        keys_map = plan_utils.purge_excess_keys(max_keys, keys_map)
        self.assertEqual(max_keys, len(keys_map))

    def test_purge_excess_keys_should_not_purge_if_less_than_max(self):
        keys_map = {
            password_utils.KEYSTONE_FERNET_REPO + '0': {
                'content': 'key0'},
            password_utils.KEYSTONE_FERNET_REPO + '1': {
                'content': 'key1'},
        }
        max_keys = 3
        keys_map = plan_utils.purge_excess_keys(max_keys, keys_map)
        self.assertEqual(2, len(keys_map))

    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_generate_password(self, mock_get_snmpd_readonly_user_password):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }
        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
        }
        mock_orchestration.resources.get.return_value = mock_resource
        result = plan_utils.generate_passwords(None, mock_orchestration)

        for password_param_name in constants.PASSWORD_PARAMETER_NAMES:
            self.assertTrue(password_param_name in result,
                            "%s is not in %s" % (password_param_name, result))

    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_run_passwords_exist(self, mock_get_snmpd_readonly_user_password,
                                 mock_fernet_keys_setup,
                                 mock_create_ssh_keypair):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': _EXISTING_PASSWORDS.copy()
        }
        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
        }
        mock_orchestration.resources.get.return_value = mock_resource

        result = plan_utils.generate_passwords(None, mock_orchestration)

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)

    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_placement_passwords_upgrade(self,
                                         mock_get_snmpd_readonly_user_password,
                                         mock_fernet_keys_setup,
                                         mock_create_ssh_keypair):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        passwords = _EXISTING_PASSWORDS.copy()

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': passwords
        }
        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {},
        }
        mock_orchestration.resources.get.return_value = mock_resource
        result = plan_utils.generate_passwords(None, mock_orchestration)
        self.assertEqual(
            passwords['NovaPassword'],
            result['PlacementPassword']
        )

    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_keystone_passwords_upgrade(self,
                                        mock_get_snmpd_readonly_user_password,
                                        mock_fernet_keys_setup,
                                        mock_create_ssh_keypair):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        passwords = _EXISTING_PASSWORDS.copy()
        keystone_password = passwords['KeystonePassword']
        passwords['AdminToken'] = keystone_password
        del passwords['KeystonePassword']

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': passwords
        }
        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {},
        }
        mock_orchestration.resources.get.return_value = mock_resource
        result = plan_utils.generate_passwords(None, mock_orchestration)
        self.assertEqual(
            keystone_password,
            result['KeystonePassword']
        )
        self.assertNotIn('AdminToken', result)

    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_run_rotate_no_rotate_list(
        self, mock_get_snmpd_readonly_user_password,
        mock_fernet_keys_setup, mock_create_ssh_keypair):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}
        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': _EXISTING_PASSWORDS.copy()
        }

        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
        }
        mock_orchestration.resources.get.return_value = mock_resource

        result = plan_utils.generate_passwords(None, mock_orchestration,
                                               rotate_passwords=True)

        # ensure passwords in the DO_NOT_ROTATE_LIST are not modified
        for name in constants.DO_NOT_ROTATE_LIST:
            self.assertEqual(_EXISTING_PASSWORDS[name], result[name])

        # ensure all passwords are generated
        for name in constants.PASSWORD_PARAMETER_NAMES:
            self.assertTrue(name in result, "%s is not in %s" % (name, result))

        # ensure new passwords have been generated
        self.assertNotEqual(_EXISTING_PASSWORDS, result)

    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_run_rotate_with_rotate_list(
        self, mock_get_snmpd_readonly_user_password,
        mock_fernet_keys_setup, mock_create_ssh_keypair):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': _EXISTING_PASSWORDS.copy()
        }

        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
        }
        mock_orchestration.resources.get.return_value = mock_resource
        rotate_list = [
            'BarbicanPassword',
            'AdminPassword',
            'CeilometerMeteringSecret',
            'NovaPassword',
            'MysqlRootPassword'
        ]

        result = plan_utils.generate_passwords(None, mock_orchestration,
                                               rotate_passwords=True,
                                               rotate_pw_list=rotate_list)

        # ensure only specified passwords are regenerated
        for name in constants.PASSWORD_PARAMETER_NAMES:
            self.assertTrue(name in result, "%s is not in %s" % (name, result))
            if name in rotate_list:
                self.assertNotEqual(_EXISTING_PASSWORDS[name], result[name])
            else:
                self.assertEqual(_EXISTING_PASSWORDS[name], result[name])

    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_passwords_exist_in_heat(
        self, mock_get_snmpd_readonly_user_password,
        mock_fernet_keys_setup, mock_create_ssh_keypair):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        existing_passwords = _EXISTING_PASSWORDS.copy()
        existing_passwords["AdminPassword"] = 'ExistingPasswordInHeat'

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': existing_passwords
        }

        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
        }
        mock_orchestration.resources.get.return_value = mock_resource

        result = plan_utils.generate_passwords(None, mock_orchestration)
        self.assertEqual(existing_passwords, result)
