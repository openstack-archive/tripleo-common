# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

import collections

import mock
from testtools import matchers

from tripleo_common import exception
from tripleo_common.tests import base
from tripleo_common.utils import nodes


class DriverInfoTest(base.TestCase):
    def setUp(self):
        super(DriverInfoTest, self).setUp()
        self.driver_info = nodes.DriverInfo(
            'foo',
            mapping={
                'pm_1': 'foo_1',
                'pm_2': 'foo_2'
            },
            deprecated_mapping={
                'pm_3': 'foo_3'
            })

    def test_convert_key(self):
        self.assertEqual('foo_1', self.driver_info.convert_key('pm_1'))
        self.assertEqual('foo_42', self.driver_info.convert_key('foo_42'))
        self.assertIsNone(self.driver_info.convert_key('bar_baz'))

    @mock.patch.object(nodes.LOG, 'warning', autospec=True)
    def test_convert_key_deprecated(self, mock_log):
        self.assertEqual('foo_3', self.driver_info.convert_key('pm_3'))
        self.assertTrue(mock_log.called)

    @mock.patch.object(nodes.LOG, 'warning', autospec=True)
    def test_convert_key_pm_unsupported(self, mock_log):
        self.assertIsNone(self.driver_info.convert_key('pm_42'))
        self.assertTrue(mock_log.called)

    def test_convert(self):
        result = self.driver_info.convert({'pm_1': 'val1',
                                           'foo_42': 42,
                                           'unknown': 'foo'})
        self.assertEqual({'foo_1': 'val1', 'foo_42': 42}, result)


class PrefixedDriverInfoTest(base.TestCase):
    def setUp(self):
        super(PrefixedDriverInfoTest, self).setUp()
        self.driver_info = nodes.PrefixedDriverInfo(
            'foo', deprecated_mapping={'pm_d': 'foo_d'})

    def test_convert_key(self):
        keys = {'pm_addr': 'foo_address',
                'pm_user': 'foo_username',
                'pm_password': 'foo_password',
                'foo_something': 'foo_something',
                'pm_d': 'foo_d'}
        for key, expected in keys.items():
            self.assertEqual(expected, self.driver_info.convert_key(key))

        for key in ('unknown', 'pm_port'):
            self.assertIsNone(self.driver_info.convert_key(key))

    def test_unique_id_from_fields(self):
        fields = {'pm_addr': 'localhost',
                  'pm_user': 'user',
                  'pm_password': '123456',
                  'pm_port': 42}
        self.assertEqual('localhost',
                         self.driver_info.unique_id_from_fields(fields))

    def test_unique_id_from_node(self):
        node = mock.Mock(driver_info={'foo_address': 'localhost',
                                      'foo_port': 42})
        self.assertEqual('localhost',
                         self.driver_info.unique_id_from_node(node))


class PrefixedDriverInfoTestWithPort(base.TestCase):
    def setUp(self):
        super(PrefixedDriverInfoTestWithPort, self).setUp()
        self.driver_info = nodes.PrefixedDriverInfo(
            'foo', deprecated_mapping={'pm_d': 'foo_d'},
            has_port=True)

    def test_convert_key_with_port(self):
        keys = {'pm_addr': 'foo_address',
                'pm_user': 'foo_username',
                'pm_password': 'foo_password',
                'foo_something': 'foo_something',
                'pm_d': 'foo_d',
                'pm_port': 'foo_port'}
        for key, expected in keys.items():
            self.assertEqual(expected, self.driver_info.convert_key(key))

        self.assertIsNone(self.driver_info.convert_key('unknown'))

    def test_unique_id_from_fields(self):
        fields = {'pm_addr': 'localhost',
                  'pm_user': 'user',
                  'pm_password': '123456',
                  'pm_port': 42}
        self.assertEqual('localhost:42',
                         self.driver_info.unique_id_from_fields(fields))

    def test_unique_id_from_node(self):
        node = mock.Mock(driver_info={'foo_address': 'localhost',
                                      'foo_port': 42})
        self.assertEqual('localhost:42',
                         self.driver_info.unique_id_from_node(node))


class iBootDriverInfoTest(base.TestCase):
    def setUp(self):
        super(iBootDriverInfoTest, self).setUp()
        self.driver_info = nodes.iBootDriverInfo()

    def test_unique_id_from_fields(self):
        fields = {'pm_addr': 'localhost',
                  'pm_user': 'user',
                  'pm_password': '123456',
                  'pm_port': 42,
                  'iboot_relay_id': 'r1'}
        self.assertEqual('localhost:42#r1',
                         self.driver_info.unique_id_from_fields(fields))

    def test_unique_id_from_fields_no_relay(self):
        fields = {'pm_addr': 'localhost',
                  'pm_user': 'user',
                  'pm_password': '123456',
                  'pm_port': 42}
        self.assertEqual('localhost:42',
                         self.driver_info.unique_id_from_fields(fields))

    def test_unique_id_from_node(self):
        node = mock.Mock(driver_info={'iboot_address': 'localhost',
                                      'iboot_port': 42,
                                      'iboot_relay_id': 'r1'})
        self.assertEqual('localhost:42#r1',
                         self.driver_info.unique_id_from_node(node))

    def test_unique_id_from_node_no_relay(self):
        node = mock.Mock(driver_info={'iboot_address': 'localhost',
                                      'iboot_port': 42})
        self.assertEqual('localhost:42',
                         self.driver_info.unique_id_from_node(node))


class FindNodeHandlerTest(base.TestCase):
    def test_found(self):
        test = [('fake', 'fake'),
                ('fake_pxe', 'fake'),
                ('pxe_ssh', 'ssh'),
                ('pxe_ipmitool', 'ipmi'),
                ('pxe_ilo', 'ilo'),
                ('agent_irmc', 'irmc')]
        for driver, prefix in test:
            handler = nodes._find_node_handler({'pm_type': driver})
            self.assertEqual(prefix, handler._prefix)

    def test_no_driver(self):
        self.assertRaises(exception.InvalidNode,
                          nodes._find_node_handler, {})

    def test_unknown_driver(self):
        self.assertRaises(exception.InvalidNode,
                          nodes._find_node_handler, {'pm_type': 'foobar'})


class NodeProvisionStateTest(base.TestCase):

    def test_wait_for_provision_state(self):
        baremetal_client = mock.Mock()
        baremetal_client.node.get.return_value = mock.Mock(
            provision_state="available", last_error=None)
        nodes.wait_for_provision_state(baremetal_client, 'UUID', "available")

    def test_wait_for_provision_state_not_found(self):
        baremetal_client = mock.Mock()
        baremetal_client.node.get.side_effect = exception.InvalidNode("boom")
        self.assertRaises(
            exception.InvalidNode,
            nodes.wait_for_provision_state,
            baremetal_client, 'UUID', "enroll")

    def test_wait_for_provision_state_timeout(self):
        baremetal_client = mock.Mock()
        baremetal_client.node.get.return_value = mock.Mock(
            provision_state="not what we want", last_error=None)
        self.assertRaises(
            exception.Timeout,
            nodes.wait_for_provision_state,
            baremetal_client, 'UUID', "available", loops=1, sleep=0.01)

    def test_wait_for_provision_state_fail(self):
        baremetal_client = mock.Mock()
        baremetal_client.node.get.return_value = mock.Mock(
            provision_state="enroll",
            last_error="node on fire; returning to previous state.")
        self.assertRaises(
            exception.StateTransitionFailed,
            nodes.wait_for_provision_state,
            baremetal_client, 'UUID', "available", loops=1, sleep=0.01)

    @mock.patch('tripleo_common.utils.nodes.wait_for_provision_state')
    def test_set_nodes_state(self, wait_for_state_mock):

        wait_for_state_mock.return_value = True
        bm_client = mock.Mock()

        # One node already deployed, one in the manageable state after
        # introspection.
        node_list = [
            mock.Mock(uuid="ABCDEFGH", provision_state="active"),
            mock.Mock(uuid="IJKLMNOP", provision_state="manageable")
        ]

        skipped_states = ('active', 'available')
        affected_nodes = nodes.set_nodes_state(bm_client, node_list, 'provide',
                                               'available', skipped_states)
        uuids = [node.uuid for node in affected_nodes]

        bm_client.node.set_provision_state.assert_has_calls([
            mock.call('IJKLMNOP', 'provide'),
        ])

        self.assertEqual(uuids, ['IJKLMNOP', ])


class NodesTest(base.TestCase):

    def _get_node(self):
        return {'cpu': '1', 'memory': '2048', 'disk': '30', 'arch': 'amd64',
                'mac': ['aaa'], 'pm_addr': 'foo.bar', 'pm_user': 'test',
                'pm_password': 'random', 'pm_type': 'pxe_ssh', 'name': 'node1',
                'capabilities': 'num_nics:6'}

    def test_register_all_nodes_ironic_no_hw_stats(self):
        node_list = [self._get_node()]

        # Remove the hardware stats from the node dictionary
        node_list[0].pop("cpu")
        node_list[0].pop("memory")
        node_list[0].pop("disk")
        node_list[0].pop("arch")

        # Node properties should be created with empty string values for the
        # hardware statistics
        node_properties = {"capabilities": "num_nics:6"}

        ironic = mock.MagicMock()
        new_nodes = nodes.register_all_nodes(node_list, client=ironic)
        self.assertEqual([ironic.node.create.return_value], new_nodes)
        pxe_node_driver_info = {"ssh_address": "foo.bar",
                                "ssh_username": "test",
                                "ssh_key_contents": "random",
                                "ssh_virt_type": "virsh"}
        pxe_node = mock.call(driver="pxe_ssh",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             properties=node_properties)
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa')
        ironic.node.create.assert_has_calls([pxe_node, mock.ANY])
        ironic.port.create.assert_has_calls([port_call])

    def test_register_all_nodes(self):
        node_list = [self._get_node()]
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        ironic = mock.MagicMock()
        nodes.register_all_nodes(node_list, client=ironic)
        pxe_node_driver_info = {"ssh_address": "foo.bar",
                                "ssh_username": "test",
                                "ssh_key_contents": "random",
                                "ssh_virt_type": "virsh"}
        pxe_node = mock.call(driver="pxe_ssh",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             properties=node_properties)
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa')
        ironic.node.create.assert_has_calls([pxe_node, mock.ANY])
        ironic.port.create.assert_has_calls([port_call])

    def test_register_all_nodes_kernel_ramdisk(self):
        node_list = [self._get_node()]
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        ironic = mock.MagicMock()
        glance = mock.MagicMock()
        image = collections.namedtuple('image', ['id'])
        glance.images.find.side_effect = (image('kernel-123'),
                                          image('ramdisk-999'))
        nodes.register_all_nodes(node_list, client=ironic,
                                 glance_client=glance, kernel_name='bm-kernel',
                                 ramdisk_name='bm-ramdisk')
        pxe_node_driver_info = {"ssh_address": "foo.bar",
                                "ssh_username": "test",
                                "ssh_key_contents": "random",
                                "ssh_virt_type": "virsh",
                                "deploy_kernel": "kernel-123",
                                "deploy_ramdisk": "ramdisk-999"}
        pxe_node = mock.call(driver="pxe_ssh",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             properties=node_properties)
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa')
        ironic.node.create.assert_has_calls([pxe_node, mock.ANY])
        ironic.port.create.assert_has_calls([port_call])

    def test_register_all_nodes_uuid(self):
        node_list = [self._get_node()]
        node_list[0]['uuid'] = 'abcdef'
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        ironic = mock.MagicMock()
        nodes.register_all_nodes(node_list, client=ironic)
        pxe_node_driver_info = {"ssh_address": "foo.bar",
                                "ssh_username": "test",
                                "ssh_key_contents": "random",
                                "ssh_virt_type": "virsh"}
        pxe_node = mock.call(driver="pxe_ssh",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             properties=node_properties,
                             uuid="abcdef")
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa')
        ironic.node.create.assert_has_calls([pxe_node, mock.ANY])
        ironic.port.create.assert_has_calls([port_call])

    def test_register_all_nodes_caps_dict(self):
        node_list = [self._get_node()]
        node_list[0]['capabilities'] = {
            'num_nics': 7
        }
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:7"}
        ironic = mock.MagicMock()
        nodes.register_all_nodes(node_list, client=ironic)
        pxe_node_driver_info = {"ssh_address": "foo.bar",
                                "ssh_username": "test",
                                "ssh_key_contents": "random",
                                "ssh_virt_type": "virsh"}
        pxe_node = mock.call(driver="pxe_ssh",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             properties=node_properties)
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa')
        ironic.node.create.assert_has_calls([pxe_node, mock.ANY])
        ironic.port.create.assert_has_calls([port_call])

    def test_register_update(self):
        node = self._get_node()
        ironic = mock.MagicMock()
        node_map = {'mac': {'aaa': 1}}

        def side_effect(*args, **kwargs):
            update_patch = [
                {'path': '/name', 'value': 'node1'},
                {'path': '/driver_info/ssh_key_contents', 'value': 'random'},
                {'path': '/driver_info/ssh_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/driver_info/ssh_username', 'value': 'test'},
                {'path': '/driver_info/ssh_virt_type', 'value': 'virsh'}]
            for key in update_patch:
                key['op'] = 'add'
            self.assertThat(update_patch,
                            matchers.MatchesSetwise(*(map(matchers.Equals,
                                                          args[1]))))
            return mock.Mock(uuid='uuid1')

        ironic.node.update.side_effect = side_effect
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)
        ironic.node.update.assert_called_once_with(1, mock.ANY)

    def test_register_update_with_images(self):
        node = self._get_node()
        node['kernel_id'] = 'image-k'
        node['ramdisk_id'] = 'image-r'
        ironic = mock.MagicMock()
        node_map = {'mac': {'aaa': 1}}

        def side_effect(*args, **kwargs):
            update_patch = [
                {'path': '/name', 'value': 'node1'},
                {'path': '/driver_info/ssh_key_contents', 'value': 'random'},
                {'path': '/driver_info/ssh_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/driver_info/deploy_kernel', 'value': 'image-k'},
                {'path': '/driver_info/deploy_ramdisk', 'value': 'image-r'},
                {'path': '/driver_info/ssh_username', 'value': 'test'},
                {'path': '/driver_info/ssh_virt_type', 'value': 'virsh'}]
            for key in update_patch:
                key['op'] = 'add'
            self.assertThat(update_patch,
                            matchers.MatchesSetwise(*(map(matchers.Equals,
                                                          args[1]))))
            return mock.Mock(uuid='uuid1')

        ironic.node.update.side_effect = side_effect
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)
        ironic.node.update.assert_called_once_with(1, mock.ANY)

    def _update_by_type(self, pm_type):
        ironic = mock.MagicMock()
        node_map = {'mac': {}, 'pm_addr': {}}
        node = self._get_node()
        node['pm_type'] = pm_type
        node_map['pm_addr']['foo.bar'] = ironic.node.get.return_value.uuid
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)
        ironic.node.update.assert_called_once_with(
            ironic.node.get.return_value.uuid, mock.ANY)

    def test_update_node_ironic_pxe_ipmitool(self):
        self._update_by_type('pxe_ipmitool')

    def test_update_node_ironic_pxe_drac(self):
        self._update_by_type('pxe_drac')

    def test_update_node_ironic_pxe_ilo(self):
        self._update_by_type('pxe_ilo')

    def test_update_node_ironic_pxe_irmc(self):
        self._update_by_type('pxe_irmc')

    def test_register_node_update(self):
        node = self._get_node()
        node['mac'][0] = node['mac'][0].upper()
        ironic = mock.MagicMock()
        node_map = {'mac': {'aaa': 1}}

        def side_effect(*args, **kwargs):
            update_patch = [
                {'path': '/name', 'value': 'node1'},
                {'path': '/driver_info/ssh_key_contents', 'value': 'random'},
                {'path': '/driver_info/ssh_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/driver_info/ssh_username', 'value': 'test'},
                {'path': '/driver_info/ssh_virt_type', 'value': 'virsh'}]
            for key in update_patch:
                key['op'] = 'add'
            self.assertThat(update_patch,
                            matchers.MatchesSetwise(*(map(matchers.Equals,
                                                          args[1]))))
            return mock.Mock(uuid='uuid1')

        ironic.node.update.side_effect = side_effect
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)
        ironic.node.update.assert_called_once_with(1, mock.ANY)

    def test_register_node_update_with_uuid(self):
        node = self._get_node()
        node['uuid'] = 'abcdef'
        ironic = mock.MagicMock()
        node_map = {'uuids': {'abcdef'}}

        def side_effect(*args, **kwargs):
            update_patch = [
                {'path': '/name', 'value': 'node1'},
                {'path': '/driver_info/ssh_key_contents', 'value': 'random'},
                {'path': '/driver_info/ssh_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/driver_info/ssh_username', 'value': 'test'},
                {'path': '/driver_info/ssh_virt_type', 'value': 'virsh'}]
            for key in update_patch:
                key['op'] = 'add'
            self.assertThat(update_patch,
                            matchers.MatchesSetwise(*(map(matchers.Equals,
                                                          args[1]))))
            return mock.Mock(uuid='abcdef')

        ironic.node.update.side_effect = side_effect
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)
        ironic.node.update.assert_called_once_with('abcdef', mock.ANY)

    def test_register_ironic_node_int_values(self):
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        node = self._get_node()
        node['cpu'] = 1
        node['memory'] = 2048
        node['disk'] = 30
        client = mock.MagicMock()
        nodes.register_ironic_node(node, client=client)
        client.node.create.assert_called_once_with(driver=mock.ANY,
                                                   name='node1',
                                                   properties=node_properties,
                                                   driver_info=mock.ANY)

    def test_register_ironic_node_fake_pxe(self):
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        node = self._get_node()
        for v in ('pm_addr', 'pm_user', 'pm_password'):
            del node[v]
        node['pm_type'] = 'fake_pxe'
        client = mock.MagicMock()
        nodes.register_ironic_node(node, client=client)
        client.node.create.assert_called_once_with(driver='fake_pxe',
                                                   name='node1',
                                                   properties=node_properties,
                                                   driver_info={})

    def test_register_ironic_node_pxe_ucs(self):
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        node = self._get_node()
        node['pm_type'] = 'pxe_ucs'
        client = mock.MagicMock()
        nodes.register_ironic_node(node, client=client)
        client.node.create.assert_called_once_with(
            driver='pxe_ucs', name='node1', properties=node_properties,
            driver_info={'ucs_password': 'random', 'ucs_address': 'foo.bar',
                         'ucs_username': 'test'})

    def test_register_ironic_node_update_int_values(self):
        node = self._get_node()
        ironic = mock.MagicMock()
        node['cpu'] = 1
        node['memory'] = 2048
        node['disk'] = 30
        node_map = {'mac': {'aaa': 1}}

        def side_effect(*args, **kwargs):
            update_patch = [
                {'path': '/name', 'value': 'node1'},
                {'path': '/driver_info/ssh_key_contents', 'value': 'random'},
                {'path': '/driver_info/ssh_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/driver_info/ssh_username', 'value': 'test'},
                {'path': '/driver_info/ssh_virt_type', 'value': 'virsh'}]
            for key in update_patch:
                key['op'] = 'add'
            self.assertThat(update_patch,
                            matchers.MatchesSetwise(*(map(matchers.Equals,
                                                      args[1]))))
            return mock.Mock(uuid='uuid1')

        ironic.node.update.side_effect = side_effect
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)

    def test_clean_up_extra_nodes_ironic(self):
        node = collections.namedtuple('node', ['uuid'])
        client = mock.MagicMock()
        client.node.list.return_value = [node('foobar')]
        seen = [node('abcd')]
        nodes._clean_up_extra_nodes(seen, client, remove=True)
        client.node.delete.assert_called_once_with('foobar')

    def test__get_node_id_fake_pxe(self):
        node = self._get_node()
        node['pm_type'] = 'fake_pxe'
        handler = nodes._find_driver_handler('fake_pxe')
        node_map = {'mac': {'aaa': 'abcdef'}, 'pm_addr': {}}
        self.assertEqual('abcdef', nodes._get_node_id(node, handler, node_map))

    def test__get_node_id_conflict(self):
        node = self._get_node()
        handler = nodes._find_driver_handler('pxe_ipmitool')
        node_map = {'mac': {'aaa': 'abcdef'},
                    'pm_addr': {'foo.bar': 'defabc'}}
        self.assertRaises(exception.InvalidNode,
                          nodes._get_node_id,
                          node, handler, node_map)

    def test_get_node_id_valid_duplicate(self):
        node = self._get_node()
        handler = nodes._find_driver_handler('pxe_ipmitool')
        node_map = {'mac': {'aaa': 'id'},
                    'pm_addr': {'foo.bar': 'id'}}
        self.assertEqual('id', nodes._get_node_id(node, handler, node_map))


class TestPopulateNodeMapping(base.TestCase):
    def test_populate_node_mapping_ironic(self):
        client = mock.MagicMock()
        ironic_node = collections.namedtuple('node', ['uuid', 'driver',
                                             'driver_info'])
        ironic_port = collections.namedtuple('port', ['address'])
        node1 = ironic_node('abcdef', 'pxe_ssh', None)
        node2 = ironic_node('fedcba', 'pxe_ipmitool',
                            {'ipmi_address': '10.0.1.2'})
        client.node.list_ports.side_effect = ([ironic_port('aaa')],
                                              [])
        client.node.list.return_value = [node1, node2]
        expected = {'mac': {'aaa': 'abcdef'},
                    'pm_addr': {'10.0.1.2': 'fedcba'},
                    'uuids': {'abcdef', 'fedcba'}}
        self.assertEqual(expected, nodes._populate_node_mapping(client))

    def test_populate_node_mapping_ironic_fake_pxe(self):
        client = mock.MagicMock()
        ironic_node = collections.namedtuple('node', ['uuid', 'driver',
                                             'driver_info'])
        ironic_port = collections.namedtuple('port', ['address'])
        node = ironic_node('abcdef', 'fake_pxe', None)
        client.node.list_ports.return_value = [ironic_port('aaa')]
        client.node.list.return_value = [node]
        expected = {'mac': {'aaa': 'abcdef'}, 'pm_addr': {},
                    'uuids': {'abcdef'}}
        self.assertEqual(expected, nodes._populate_node_mapping(client))
