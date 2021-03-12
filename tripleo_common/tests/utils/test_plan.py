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

import json
import os
import sys
from unittest import mock
import zlib

import yaml

import six
from swiftclient import exceptions as swiftexceptions

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
  ZaqarPassword: zzzz
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
    'MistralPassword': 'VFJeqBKbatYhQm9jja67hufft',
    'BarbicanPassword': 'MGGQBtgKT7FnywvkcdMwE9nhx',
    'BarbicanSimpleCryptoKek': 'dGhpcnR5X3R3b19ieXRlX2tleWJsYWhibGFoYmxhaGg=',
    'AdminPassword': 'jFmY8FTpvtF2e4d4ReXvmUP8k',
    'CeilometerMeteringSecret': 'CbHTGK4md4Cc8P8ZyzTns6wry',
    'ZaqarPassword': 'bbFgCTFbAH8vf9n3xvZCP8aMR',
    'NovaPassword': '7dZATgVPwD7Ergs9kTTDMCr7F',
    'MysqlRootPassword': 'VqJYpEdKks',
    'RabbitCookie': 'BqJYpEdKksAqJYpEdKks',
    'HeatAuthEncryptionKey': '9xZXehsKc2HbmFFMKjuqxTJHn',
    'PcsdPassword': 'KjEzeitus8eu751a',
    'HorizonSecret': 'mjEzeitus8eu751B',
    'NovajoinPassword': '7dZATgVPwD7Ergs9kTTDMCr7F',
    'IronicPassword': '4hFDgn9ANeVfuqk84pHpD4ksa',
    'RedisPassword': 'xjj3QZDcUQmU6Q7NzWBHRUhGd',
    'SaharaPassword': 'spFvYGezdFwnTk7NPxgYTbUPh',
    'AdminToken': 'jq6G6HyZtj7dcZEvuyhAfjutM',
    'CinderPassword': 'dcxC3xyUcrmvzfrrxpAd3REcm',
    'CongressPassword': 'DwcKvMqXMuNYYFU4zTCuG4234',
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
    'PankoPassword': 'cVZXehsSc2KdmFFMKDudxTLKn',
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
    'CephClusterFSID': u'97c16f44-b62c-11e6-aed3-185e0f73fdc5',
    'Ec2ApiPassword': 'FPvz2WiWxrHVWrmSSvv44bqmr',
    'EtcdInitialClusterToken': 'fcVZXehsSc2KdmFFMKDudxTLKa',
    'PacemakerRemoteAuthkey':
        'bCfHQx4fX7FqENVBbDfBnKvf6FTH6mPfVdNjfzakEjuF4UbmZJHAxWdheEr6feEyZmtM'
        'XEd4w3qM8nMVrzjnDCmqAFDmMDQfKcuNgTnqGnkbVUDGpym67Ry4vNCPHyp9tGGyfjNX'
        't66csYZTYUHPv6jdJk4HWBjE66v8B3nRpc3FePQ8DRMWX4hcGFNNxapJu7v2frKwq4tD'
        '78cc7aPPMGPn8kR3mj7kMP8Ah8VVGXJEtybEvRg4sQ67zEkAzfKggrpXYPK2Qvv9sHKp'
        't2VjwZBHTvWKarJjyeMTqbzJyW6JTbm62gqZCr9afZRFQug62pPRduvkUNfUYNPNpqjy'
        'yznmeAZPxVseU3jJVxKrxdrgzavKEMtW6BbTmw86j8wuUdaWgRccRGVUQvtQ4p9kXHAy'
        'eXVduZvpvxFtbKvfNTvf6qCuJ8qeQp2TwJQPHUYHkxZYrpAA7fZUzNCZR2tFFdZzWGt2'
        'PEnYvYts4m7Fp9XEmNm7Jyme38CBfnaVERmTMRvHkq3EE2Amsc72aDdzeVRjR3xRgMNJ'
        '2cEEWqatZXveHxJr6VmBNWJUyvPrfmVegwtKCGJND8d3Ysruy7GCn6zcrNY7d84aDk3P'
        'q7NyZfRYrGcNDKJuzNWH8UNwGP68uQsUUrV9NVTVpB2sRPG2tJm3unYqekUg3KYXu46J'
        'mANxqgrqDv6vPx6NCPdUXZTXFaesQatKRkkf3nZFqZQJXZVbkudTmrPYyRQAjvWuAmrY'
        '6RcFFmygeFnhAxhwXNdge9tEfsfPeQ4GMxa8Amj2fMjmNvQXFfQ8uxMUnusDmhbwCRKM'
        'CvN2dNE92MaQge34vtxsueyDEmbuVE9sNRD3EQBRwx8nktgRwKHfRZJ3BX8f9XMaQe2e'
        'ZfGjtUNkbgKdCyYgEwEybXKPfevDnxFvbZMpJx4fqqCAbAZud9RnAuvqHgFbKHXcVEE4'
        'nRmgJmdqJsRsTkYPpYkKN9rssEDCXr9HFjbenkxXcUe8afrTvKAzwBvbDWcjYBEQKbuY'
        '6Ptm9VJrjutUHCPmW2sh66qvq4C9vPhVEey7FpCZDEyYUPrjRfhKjxEFNBKWpcZzvmT2'
        'nRmgJmdqJsRsTkYPpYkKN9rssEDCXr9HFjbenkxXcUe8afrTvKAzwBvbDWcjYBEQKbuY'
        '2cEEWqatZXveHxJr6VmBNWJUyvPrfmVegwtKCGJND8d3Ysruy7GCn6zcrNY7d84aDk3P'
        'VRE4aqMfuY72xFacxXHjvWagEGQEYtkMtQnsh7XAMGuazT3pkppeUTyDbKTY2Dz7Quc3'
        '8UKaw8ece6fTXWpjX2EYrsd4qzvhC6eEPdgnpmzjqmuG8YqEAUZ7dYADgAhTkBQsNct8'
        'btQsQDYD4PBjxG2KWAZ9vgTsvBpjjEVcrPfWgwZKJTAZWfWq2u7nT4N2t39EYmQEzbEf'
        '8UKaw8ece6fTXWpjX2EYrsd4qzvhC6eEPdgnpmzjqmuG8YqEAUZ7dYADgAhTkBQsNct8'
        'DkCF3DJ49jjZm9N4EKnKGGXD7XkFE79AFRGPUw4gXpeQCtUXyEugUErqMjqgJjC7ykdg'
        'zz7txnzYfRaKHNVs4r4GwNEHRHt7VcTuT3WBcbE4skQgjMnttgP7hts7dMU7PA8kRrfq'
        'BKdkPkUwqQ9Xn4zrysY4GvJQHWXxD6Tyqf9PZaz4xbUmsvtuY7NAz27U2aT3EA9XCgfn'
        '2cEEWqatZXveHxJr6VmBNWJUyvPrfmVegwtKCGJND8d3Ysruy7GCn6zcrNY7d84aDk3P'
        'CEfTJQz342nwRMY4DCuhawz4cnrWwxgsnVPCbeXYH4RcgswVsk9edxKkYMkpTwpcKf6n'
        'nRmgJmdqJsRsTkYPpYkKN9rssEDCXr9HFjbenkxXcUe8afrTvKAzwBvbDWcjYBEQKbuY'
        '6Ptm9VJrjutUHCPmW2sh66qvq4C9vPhVEey7FpCZDEyYUPrjRfhKjxEFNBKWpcZzvmT2'
        'VRE4aqMfuY72xFacxXHjvWagEGQEYtkMtQnsh7XAMGuazT3pkppeUTyDbKTY2Dz7Quc3'
        '8UKaw8ece6fTXWpjX2EYrsd4qzvhC6eEPdgnpmzjqmuG8YqEAUZ7dYADgAhTkBQsNct8'
        'btQsQDYD4PBjxG2KWAZ9vgTsvBpjjEVcrPfWgwZKJTAZWfWq2u7nT4N2t39EYmQEzbEf'
        'DkCF3DJ49jjZm9N4EKnKGGXD7XkFE79AFRGPUw4gXpeQCtUXyEugUErqMjqgJjC7ykdg'
        'zz7txnzYfRaKHNVs4r4GwNEHRHt7VcTuT3WBcbE4skQgjMnttgP7hts7dMU7PA8kRrfq'
        'BKdkPkUwqQ9Xn4zrysY4GvJQHWXxD6Tyqf9PZaz4xbUmsvtuY7NAz27U2aT3EA9XCgfn'
        '2cEEWqatZXveHxJr6VmBNWJUyvPrfmVegwtKCGJND8d3Ysruy7GCn6zcrNY7d84aDk3P'
        'CEfTJQz342nwRMY4DCuhawz4cnrWwxgsnVPCbeXYH4RcgswVsk9edxKkYMkpTwpcKf6n'
        'E2dhquqdKVTAYf7YKbTfFVsRwqykkPduKXuPwVDjbCqdEJPcmnRJAJkwkQCWgukpvzzm'
        'DKFVYxncxmzKgEN27VtgfpsXWBJ2jaxMeQCXb2rbjkVcaypyaETQ3Wkw98EptNAKRcjM'
        'E2dhquqdKVTAYf7YKbTfFVsRwqykkPduKXuPwVDjbCqdEJPcmnRJAJkwkQCWgukpvzzm'
        'zZJ2xFdfNYh7RZ7EgAAbY8Tqy3j2c9c6HNmXwAVV6dzPTrE4FHcKZGg76anGchczF9ev'
        'AG8RHQ7ea2sJhXqBmGsmEj6Q84TN9E7pgmtAtmVAA38AYsQBNZUMYdMcmBdpV9w7G3NZ'
        'mEU8R8uWqx6w3NzzqsMg78bnhCR7sdWDkhuEp2M8fYWmqujYFNYvzz6BcHNKQyrWETRD'
        'E2dhquqdKVTAYf7YKbTfFVsRwqykkPduKXuPwVDjbCqdEJPcmnRJAJkwkQCWgukpvzzm'
        'zaTdNWgM7wsXGkvgYVNdTWnReCPXJUN3yQwrvApZzdaF86QaeYwXW7qqEJrqmwpUUbw2'
        'JHkmvJB4AWtVhDc9etzUqfuTaqMyXwxFEWvht3RDTDx8dfQ3Ek8BD4QP4BtUQeQJpfsG'
        'FEJeQQYVcBxqVuK26xJrERUDmeNw8KWKBCrYPPy48cjCFdgZHz3cNet6bwJMdsgKMpZT'
        'erdYy9nqBw6FRZ37rRMtxmrcB4VsWHbf4HjdPRpu4xyJTqMThnXWa8nPDde3C9wCuKkQ'
        '23k2zDYsMeHc6KD93vm7Ky48v3veYEuJvNNxQPyyCZ9XNnpGsWrqsVduCswR4MQpp6yJ'
        'RBmwbMYbuEjwJy9UuZxa9bQV4GqYFnVuETC6bXaT9uauWdaa2TrbuuXx3WWdmRGd4Rqh'
        'Z3NA9Kqx9pTQHe3KGZ2tFejsJqNvjJvFX94eVeMGDgHjtJzDdxp9NWYtG6v9zABGRzVF'
        'MqJX6nhhBPbsvjpswcgJq3ZXxzmWFJmvjECghGrbG6bKawtv4aYhMeaHagfMP8W6KrTy'
        'uGxWUhcEhfygjE4truAkjfKCtzzVtTcBArbWMny6HWMp6TAen3f6hEB6kBb7pgvKxkND'
        '3JxueYBZvDeq4WWtRzUjcFF2qhEjwrtuCJhy3WMXX3MN6nFDtYRTHZGdPqyatW9Jcc8t'
        '7gCMWMVzYyNuXZ2A6rwX6Umv8g3mBuwnrwKXEFTZkPCAZMxk3A6MTmMcJCVy3hw6MmRM'
        'eXKyhFxRcKWraysTQG7hd9kP8DeJZNDurYDJwqrh6cwDwaMhBfTgnxTBeyjwpbCJK2FD'
        'Jg2vFWPmTJ37gDMdwxWCMRQ9kyqz9PJZ4Xn2MPxMhNqT3Hb39YshryqnbvBagHbqYx9M'
        'r4ZKJpKya34JMaPambzg2pKRDd2WdFCZcdHTFyqxxzJbjXM2gjfBZ2strUNqWvQYNTw8'
        'QttkuxyeQTgHupKNaZF6y7rDyf7mbNR9DaPXpBQuZ7un6KDj2Dfh7yvfhPk8cHG7n9pb'
        'KEKD3sgbbKnQ8d9MsGhUtCQVed7dtjpYKsmGJmbYMvZjpGpqsfsHQfFRdCgJHnW3FdQ6'
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
        self.swift = mock.MagicMock()
        self.swift.get_object.return_value = ({}, PLAN_ENV_CONTENTS)

    def test_get_env(self):
        env = plan_utils.get_env(self.swift, self.container)

        self.swift.get_object.assert_called()
        self.assertEqual(env['template'], 'overcloud.yaml')

    def test_get_env_not_found(self):
        self.swift.get_object.side_effect = swiftexceptions.ClientException

        self. assertRaises(Exception, plan_utils.get_env, self.swift,
                           self.container)

    def test_get_user_env(self):
        self.swift.get_object.return_value = ({}, USER_ENV_CONTENTS)
        env = plan_utils.get_user_env(self.swift, self.container)

        self.swift.get_object.assert_called_with(
            self.container, 'user-environment.yaml')
        self.assertEqual(
            env['resource_registry']['OS::TripleO::Foo'], 'bar.yaml')

    def test_put_user_env(self):
        contents = {'a': 'b'}
        plan_utils.put_user_env(self.swift, self.container, contents)

        self.swift.put_object.assert_called_with(
            self.container, 'user-environment.yaml', 'a: b\n')

    def test_update_in_env(self):
        env = plan_utils.get_env(self.swift, self.container)

        updated_env = plan_utils.update_in_env(
            self.swift,
            env,
            'template',
            'updated-overcloud.yaml'
        )
        self.assertEqual(updated_env['template'], 'updated-overcloud.yaml')

        updated_env = plan_utils.update_in_env(
            self.swift,
            env,
            'parameter_defaults',
            {'another-key': 'another-value'}
        )
        self.assertEqual(updated_env['parameter_defaults'], {
            'BlockStorageCount': 42,
            'OvercloudControlFlavor': 'yummy',
            'another-key': 'another-value'
        })

        updated_env = plan_utils.update_in_env(
            self.swift,
            env,
            'parameter_defaults',
            delete_key=True
        )
        self.assertNotIn('parameter_defaults', updated_env)

        self.swift.get_object.assert_called()
        self.swift.put_object.assert_called()

    def test_write_json_temp_file(self):
        name = plan_utils.write_json_temp_file({'foo': 'bar'})
        with open(name) as f:
            self.assertEqual({'foo': 'bar'}, json.load(f))
        os.remove(name)

    @mock.patch('requests.request', autospec=True)
    def test_object_request(self, request):
        request.return_value.content = 'foo'

        content = plan_utils.object_request('GET', '/foo/bar', 'asdf1234')

        self.assertEqual('foo', content)
        request.assert_called_once_with(
            'GET', '/foo/bar', headers={'X-Auth-Token': 'asdf1234'})

    @mock.patch('tripleo_common.utils.plan.object_request',
                autospec=True)
    def test_process_environments_and_files(self, object_request):
        swift_url = 'https://192.0.2.1:8443/foo'
        url = '%s/bar' % swift_url
        object_request.return_value = 'parameter_defaults: {foo: bar}'
        swift = mock.Mock()
        swift.url = swift_url
        swift.token = 'asdf1234'

        result = plan_utils.process_environments_and_files(swift, [url])

        self.assertEqual(
            {'parameter_defaults': {'foo': 'bar'}},
            result[1]
        )
        object_request.assert_called_once_with(
            'GET',
            'https://192.0.2.1:8443/foo/bar',
            'asdf1234'
        )

    @mock.patch('tripleo_common.utils.plan.object_request',
                autospec=True)
    def test_get_template_contents(self, object_request):
        swift_url = 'https://192.0.2.1:8443/foo'
        url = '%s/bar' % swift_url
        object_request.return_value = 'heat_template_version: 2016-04-30'
        swift = mock.Mock()
        swift.url = swift_url
        swift.token = 'asdf1234'

        result = plan_utils.get_template_contents(swift, url)

        self.assertEqual(
            {'heat_template_version': '2016-04-30'},
            result[1]
        )
        object_request.assert_called_once_with(
            'GET',
            'https://192.0.2.1:8443/foo/bar',
            'asdf1234'
        )

    def test_build_env_paths(self):
        swift = mock.Mock()
        swift.url = 'https://192.0.2.1:8443/foo'
        swift.token = 'asdf1234'
        plan = {
            'version': '1.0',
            'environments': [
                {'path': 'bar.yaml'},
                {'data': {
                    'parameter_defaults': {'InlineParam': 1}}}
            ],
            'passwords': {
                'ThePassword': 'password1'
            },
            'derived_parameters': {
                'DerivedParam': 'DerivedValue',
                'MergableParam': {
                    'one': 'derived one',
                    'two': 'derived two',
                },
            },
            'parameter_defaults': {
                'Foo': 'bar',
                'MergableParam': {
                    'one': 'user one',
                    'three': 'user three',
                },
            },
            'resource_registry': {
                'Foo::Bar': 'foo_bar.yaml'
            },
        }

        env_paths, temp_env_paths = plan_utils.build_env_paths(
            swift, 'overcloud', plan)

        self.assertEqual(3, len(temp_env_paths))
        self.assertEqual(
            ['https://192.0.2.1:8443/foo/overcloud/bar.yaml'] + temp_env_paths,
            env_paths
        )

        with open(env_paths[1]) as f:
            self.assertEqual(
                {'parameter_defaults': {'InlineParam': 1}},
                json.load(f)
            )

        with open(env_paths[2]) as f:
            self.assertEqual(
                {'parameter_defaults': {
                    'ThePassword': 'password1',
                    'DerivedParam': 'DerivedValue',
                    'Foo': 'bar',
                    'MergableParam': {
                        'one': 'user one',
                        'two': 'derived two',
                        'three': 'user three',
                    }
                }},
                json.load(f)
            )

        with open(env_paths[3]) as f:
            self.assertEqual(
                {'resource_registry': {
                    'Foo::Bar': 'foo_bar.yaml'
                }},
                json.load(f)
            )

        for path in temp_env_paths:
            os.remove(path)

    def test_format_cache_key(self):
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"

        self.assertEqual(
            plan_utils.format_cache_key(container, key),
            cache_key
        )

    @mock.patch("tripleo_common.utils.keystone.get_session_and_auth")
    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_set(self, mock_conn, mock_keystone):
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        cache_container = "__cache__"
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"
        compressed_json = zlib.compress("{\"foo\": 1}".encode())

        plan_utils.cache_set(mock_swift, container, key, {"foo": 1})
        mock_swift.put_object.assert_called_once_with(
            cache_container,
            cache_key,
            compressed_json
        )
        mock_swift.delete_object.assert_not_called()

    @mock.patch("tripleo_common.utils.keystone.get_session_and_auth")
    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_set_none(self, mock_conn, mock_keystone):
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        cache_container = "__cache__"
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"

        plan_utils.cache_set(mock_swift, container, key, None)
        mock_swift.put_object.assert_not_called()
        mock_swift.delete_object.called_once_with(
            cache_container,
            cache_key
        )

    @mock.patch("tripleo_common.utils.keystone.get_session_and_auth")
    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_get_filled(self, mock_conn, mock_keystone):
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        container = "TestContainer"
        key = "testkey"
        compressed_json = zlib.compress("{\"foo\": 1}".encode())
        # test if cache has something in it
        mock_swift.get_object.return_value = ([], compressed_json)
        result = plan_utils.cache_get(mock_swift, container, key)
        self.assertEqual(result, {"foo": 1})

    @mock.patch("tripleo_common.utils.keystone.get_session_and_auth")
    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_empty(self, mock_conn, mock_keystone):
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        cache_container = "__cache__"
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"

        mock_swift.get_object.side_effect = swiftexceptions.ClientException(
            "Foo"
        )
        result = plan_utils.cache_get(mock_swift, container, key)
        self.assertFalse(result)

        # delete cache if we have a value
        plan_utils.cache_delete(mock_swift, container, key)
        mock_swift.delete_object.assert_called_once_with(
            cache_container,
            cache_key
        )

    @mock.patch("tripleo_common.utils.keystone.get_session_and_auth")
    @mock.patch("tripleo_common.actions.base.swift_client.Connection")
    def test_cache_delete(self, mock_conn, mock_keystone):
        mock_swift = mock.Mock()
        mock_conn.return_value = mock_swift

        cache_container = "__cache__"
        container = "TestContainer"
        key = "testkey"
        cache_key = "__cache_TestContainer_testkey"
        mock_swift.delete_object.side_effect = swiftexceptions.ClientException(
            "Foo"
        )
        plan_utils.cache_delete(mock_swift, container, key)
        mock_swift.delete_object.assert_called_once_with(
            cache_container,
            cache_key
        )

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

    @mock.patch('tripleo_common.utils.plan.'
                'cache_delete')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_generate_password(self, mock_get_snmpd_readonly_user_password,
                               mock_cache):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': 'overcast',
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }
        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
            'value': 'existing_value'
        }
        mock_orchestration.resources.get.return_value = mock_resource

        result = plan_utils.generate_passwords(swift, mock_orchestration)

        for password_param_name in constants.PASSWORD_PARAMETER_NAMES:
            self.assertTrue(password_param_name in result,
                            "%s is not in %s" % (password_param_name, result))

            if password_param_name in \
                    constants.LEGACY_HEAT_PASSWORD_RESOURCE_NAMES:
                self.assertEqual(result[password_param_name], 'existing_value')
            else:
                self.assertNotEqual(result[password_param_name],
                                    'existing_value')

        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get"
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_delete')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_run_passwords_exist(self, mock_get_snmpd_readonly_user_password,
                                 mock_fernet_keys_setup,
                                 mock_create_ssh_keypair,
                                 mock_cache):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'passwords': _EXISTING_PASSWORDS.copy()
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }
        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
            'value': None
        }
        mock_orchestration.resources.get.return_value = mock_resource

        result = plan_utils.generate_passwords(swift, mock_orchestration)

        # ensure old passwords used and no new generation
        self.assertEqual(_EXISTING_PASSWORDS, result)
        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get"
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_delete')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_placement_passwords_upgrade(self,
                                         mock_get_snmpd_readonly_user_password,
                                         mock_fernet_keys_setup,
                                         mock_create_ssh_keypair,
                                         mock_cache):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        passwords = _EXISTING_PASSWORDS.copy()

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'passwords': passwords
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }
        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': None,
            'value': None
        }
        mock_orchestration.resources.get.return_value = mock_resource

        result = plan_utils.generate_passwords(swift, mock_orchestration)

        self.assertEqual(
            passwords['NovaPassword'],
            result['PlacementPassword']
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_delete')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_run_rotate_no_rotate_list(
        self, mock_get_snmpd_readonly_user_password,
        mock_fernet_keys_setup, mock_create_ssh_keypair,
        mock_cache):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'passwords': _EXISTING_PASSWORDS.copy()
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }

        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
            'value': 'existing_value'
        }
        mock_orchestration.resources.get.return_value = mock_resource

        result = plan_utils.generate_passwords(swift, mock_orchestration,
                                               rotate_passwords=True)

        # ensure passwords in the DO_NOT_ROTATE_LIST are not modified
        for name in constants.DO_NOT_ROTATE_LIST:
            self.assertEqual(_EXISTING_PASSWORDS[name], result[name])

        # ensure all passwords are generated
        for name in constants.PASSWORD_PARAMETER_NAMES:
            self.assertTrue(name in result, "%s is not in %s" % (name, result))

        # ensure new passwords have been generated
        self.assertNotEqual(_EXISTING_PASSWORDS, result)
        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get"
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_delete')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_run_rotate_with_rotate_list(
        self, mock_get_snmpd_readonly_user_password,
        mock_fernet_keys_setup, mock_create_ssh_keypair,
        mock_cache):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'passwords': _EXISTING_PASSWORDS.copy()
        }, default_flow_style=False)
        swift.get_object.return_value = ({}, mock_env)

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {}
        }

        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
            'value': 'existing_value'
        }
        mock_orchestration.resources.get.return_value = mock_resource

        rotate_list = [
            'MistralPassword',
            'BarbicanPassword',
            'AdminPassword',
            'CeilometerMeteringSecret',
            'ZaqarPassword',
            'NovaPassword',
            'MysqlRootPassword'
        ]

        result = plan_utils.generate_passwords(swift, mock_orchestration,
                                               rotate_passwords=True,
                                               rotate_pw_list=rotate_list)

        # ensure only specified passwords are regenerated
        for name in constants.PASSWORD_PARAMETER_NAMES:
            self.assertTrue(name in result, "%s is not in %s" % (name, result))
            if name in rotate_list:
                self.assertNotEqual(_EXISTING_PASSWORDS[name], result[name])
            else:
                self.assertEqual(_EXISTING_PASSWORDS[name], result[name])

        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get"
        )

    @mock.patch('tripleo_common.utils.plan.'
                'cache_delete')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_ssh_keypair')
    @mock.patch('tripleo_common.utils.passwords.'
                'create_fernet_keys_repo_structure_and_keys')
    @mock.patch('tripleo_common.utils.passwords.'
                'get_snmpd_readonly_user_password')
    def test_passwords_exist_in_heat(
        self, mock_get_snmpd_readonly_user_password,
        mock_fernet_keys_setup, mock_create_ssh_keypair,
        mock_cache):

        mock_get_snmpd_readonly_user_password.return_value = "TestPassword"
        mock_create_ssh_keypair.return_value = {'public_key': 'Foo',
                                                'private_key': 'Bar'}
        mock_fernet_keys_setup.return_value = {'/tmp/foo': {'content': 'Foo'},
                                               '/tmp/bar': {'content': 'Bar'}}

        existing_passwords = _EXISTING_PASSWORDS.copy()
        existing_passwords.pop("AdminPassword")
        existing_passwords.pop("PcsdPassword")

        swift = mock.MagicMock(url="http://test.com")
        mock_env = yaml.safe_dump({
            'name': constants.DEFAULT_CONTAINER_NAME,
            'temp_environment': 'temp_environment',
            'template': 'template',
            'environments': [{u'path': u'environments/test.yaml'}],
            'passwords': existing_passwords.copy()
        }, default_flow_style=False)

        swift.get_object.return_value = ({}, mock_env)

        mock_orchestration = mock.MagicMock()
        mock_orchestration.stacks.environment.return_value = {
            'parameter_defaults': {
                'AdminPassword': 'ExistingPasswordInHeat',
                'PcsdPassword': 'MyPassword'
            }
        }

        mock_resource = mock.MagicMock()
        mock_resource.attributes = {
            'endpoint_map': {
                'PlacementPublic': {}
            },
            'value': 'existing_value'
        }
        mock_orchestration.resources.get.return_value = mock_resource

        result = plan_utils.generate_passwords(swift, mock_orchestration)

        existing_passwords["AdminPassword"] = "ExistingPasswordInHeat"
        existing_passwords["PcsdPassword"] = "MyPassword"
        # ensure old passwords used and no new generation
        self.assertEqual(existing_passwords, result)
        mock_cache.assert_called_once_with(
            swift,
            "overcloud",
            "tripleo.parameters.get"
        )

    @mock.patch("tripleo_common.utils.plan.get_role_data")
    @mock.patch("tripleo_common.utils.plan."
                "update_plan_environment")
    @mock.patch("tripleo_common.utils.plan.get_env", autospec=True)
    @mock.patch("tripleo_common.image.kolla_builder."
                "container_images_prepare_multi")
    @mock.patch("tripleo_common.image.kolla_builder.KollaImageBuilder")
    def test_update_plan_with_image_parameter(
        self, kib, prepare, get_env, mock_update_plan, grd):
        builder = kib.return_value
        builder.container_images_from_template.return_value = [{
            'imagename': 't/cb-nova-compute:liberty',
            'params': ['ContainerNovaComputeImage',
                       'ContainerNovaLibvirtConfigImage']
        }, {'imagename': 't/cb-nova-libvirt:liberty',
            'params': ['ContainerNovaLibvirtImage']}]

        plan = {
            'version': '1.0',
            'environments': [],
            'parameter_defaults': {}
        }
        role_data = [{'name': 'Controller'}]
        final_env = {'environments': [
            {'path': 'overcloud-resource-registry-puppet.yaml'},
            {'path': 'environments/containers-default-parameters.yaml'},
            {'path': 'user-environment.yaml'}
        ]}
        image_params = {
            'FooContainerImage': '192.0.2.1/foo/image',
            'ContainerNovaComputeImage': 't/cb-nova-compute:liberty',
            'ContainerNovaLibvirtConfigImage': 't/cb-nova-compute:liberty',
            'ContainerNovaLibvirtImage': 't/cb-nova-libvirt:liberty',
        }
        image_env_contents = yaml.safe_dump(
            {'parameter_defaults': image_params},
            default_flow_style=False
        )

        swift = mock.MagicMock()
        swift.get_object.return_value = role_data
        prepare.return_value = image_params
        grd.return_value = role_data

        get_env.return_value = plan
        mock_update_plan.return_value = final_env
        result = plan_utils.update_plan_environment_with_image_parameters(
            swift, container='overcloud')
        self.assertEqual(final_env, result)

        get_env.assert_called_once_with(swift, 'overcloud')
        prepare.assert_called_once_with({}, role_data, dry_run=True)
        swift.put_object.assert_called_once_with(
            'overcloud',
            'environments/containers-default-parameters.yaml',
            image_env_contents
        )

    @mock.patch("tripleo_common.utils.plan."
                "update_plan_environment")
    @mock.patch("tripleo_common.image.kolla_builder.KollaImageBuilder")
    def test_update_plan_image_parameters_default(
        self, kib, mock_update_plan):
        swift = mock.MagicMock()
        builder = kib.return_value
        builder.container_images_from_template.return_value = [{
            'imagename': 't/cb-nova-compute:liberty',
            'params': ['ContainerNovaComputeImage',
                       'ContainerNovaLibvirtConfigImage']
        }, {'imagename': 't/cb-nova-libvirt:liberty',
            'params': ['ContainerNovaLibvirtImage']}]

        final_env = {'environments': [
            {'path': 'overcloud-resource-registry-puppet.yaml'},
            {'path': 'environments/containers-default-parameters.yaml'},
            {'path': 'user-environment.yaml'}
        ]}
        mock_update_plan.return_value = final_env

        result = plan_utils.update_plan_environment_with_image_parameters(
            swift, container='overcloud', with_roledata=False)
        self.assertEqual(final_env, result)

        kib.assert_called_once_with(
            [os.path.join(sys.prefix, 'share', 'tripleo-common',
                          'container-images', 'tripleo_containers.yaml.j2')]
        )
        params = {
            'ContainerNovaComputeImage': 't/cb-nova-compute:liberty',
            'ContainerNovaLibvirtConfigImage': 't/cb-nova-compute:liberty',
            'ContainerNovaLibvirtImage': 't/cb-nova-libvirt:liberty',
        }
        expected_env = yaml.safe_dump(
            {'parameter_defaults': params},
            default_flow_style=False
        )
        swift.put_object.assert_called_once_with(
            'overcloud',
            'environments/containers-default-parameters.yaml',
            expected_env
        )
        mock_update_plan.assert_called_once_with(
            swift,
            {'environments/containers-default-parameters.yaml': True},
            container='overcloud'
        )

    def test_create_plan_container(self):
        # Setup
        container_name = 'Test-container-7'
        swift = mock.MagicMock()
        swift.get_account.return_value = [
            '', [{'name': 'test1'}, {'name': 'test2'}]]

        # Test
        plan_utils.create_plan_container(swift, container_name)

        # Verify
        swift.put_container.assert_called_once_with(
            container_name,
            headers={'x-container-meta-usage-tripleo': 'plan'}
        )

    def test_container_exists(self):
        # Setup
        container_name = 'Test-container-7'
        swift = mock.MagicMock()
        swift.get_account.return_value = [
            '', [{'name': 'Test-container-7'}, {'name': 'test2'}]]

        # Test
        error_str = ('A container with the name %s already'
                     ' exists.') % container_name
        err = self.assertRaises(RuntimeError,
                                plan_utils.create_plan_container,
                                swift, container_name)
        self.assertEquals(error_str, six.text_type(err))

    def test_run_invalid_name(self):
        # Setup
        container_name = 'Invalid_underscore'
        swift = mock.MagicMock()

        # Test
        error_str = ('The plan name must only contain '
                     'letters, numbers or dashes')
        err = self.assertRaises(RuntimeError,
                                plan_utils.create_plan_container,
                                swift, container_name)
        self.assertEquals(error_str, six.text_type(err))
