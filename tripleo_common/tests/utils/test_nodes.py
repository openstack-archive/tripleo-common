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


class RedfishDriverInfoTest(base.TestCase):
    driver_info = nodes.RedfishDriverInfo()

    def test_convert_key(self):
        keys = {'pm_addr': 'redfish_address',
                'pm_user': 'redfish_username',
                'pm_password': 'redfish_password',
                'pm_system_id': 'redfish_system_id',
                'redfish_verify_ca': 'redfish_verify_ca'}
        for key, expected in keys.items():
            self.assertEqual(expected, self.driver_info.convert_key(key))

        self.assertIsNone(self.driver_info.convert_key('unknown'))

    def test_unique_id_from_fields(self):
        for address in ['example.com',
                        'http://example.com/',
                        'https://example.com/']:
            fields = {'pm_addr': address,
                      'pm_user': 'user',
                      'pm_password': '123456',
                      'pm_system_id': '/redfish/v1/Systems/1'}
            self.assertEqual('example.com/redfish/v1/Systems/1',
                             self.driver_info.unique_id_from_fields(fields))

    def test_unique_id_from_node(self):
        for address in ['example.com',
                        'http://example.com/',
                        'https://example.com/']:
            node = mock.Mock(driver_info={
                'redfish_address': address,
                'redfish_system_id': '/redfish/v1/Systems/1'})
            self.assertEqual('example.com/redfish/v1/Systems/1',
                             self.driver_info.unique_id_from_node(node))


class oVirtDriverInfoTest(base.TestCase):
    driver_info = nodes.oVirtDriverInfo()

    def test_convert_key(self):
        keys = {'pm_addr': 'ovirt_address',
                'pm_user': 'ovirt_username',
                'pm_password': 'ovirt_password',
                'pm_vm_name': 'ovirt_vm_name',
                'ovirt_insecure': 'ovirt_insecure'}
        for key, expected in keys.items():
            self.assertEqual(expected, self.driver_info.convert_key(key))

        self.assertIsNone(self.driver_info.convert_key('unknown'))

    def test_unique_id_from_fields(self):
        fields = {'pm_addr': 'http://127.0.0.1',
                  'pm_user': 'user',
                  'pm_password': '123456',
                  'pm_vm_name': 'My VM'}
        self.assertEqual('http://127.0.0.1:My VM',
                         self.driver_info.unique_id_from_fields(fields))

    def test_unique_id_from_node(self):
        node = mock.Mock(driver_info={
            'ovirt_address': 'http://127.0.0.1',
            'ovirt_vm_name': 'My VM'})
        self.assertEqual('http://127.0.0.1:My VM',
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


class UcsDriverInfoTest(base.TestCase):
    driver_info = nodes.UcsDriverInfo()

    def test_convert_key(self):
        keys = {
            'pm_addr': 'ucs_address',
            'pm_user': 'ucs_username',
            'pm_password': 'ucs_password',
            'pm_service_profile': 'ucs_service_profile'
        }
        for key, expected in keys.items():
            self.assertEqual(expected, self.driver_info.convert_key(key))

        self.assertIsNone(self.driver_info.convert_key('unknown'))

    def test_unique_id_from_fields(self):
        fields = {
            'pm_addr': '127.0.0.1',
            'pm_user': 'user',
            'pm_password': '123456',
            "pm_service_profile": 'org-root/org-CPC/ls-CPC-test'
        }
        self.assertEqual('127.0.0.1:org-root/org-CPC/ls-CPC-test',
                         self.driver_info.unique_id_from_fields(fields))

    def test_unique_id_from_node(self):
        node = mock.Mock(
            driver_info={
                'ucs_address': '127.0.0.1',
                'ucs_username': 'user',
                'ucs_password': '123456',
                "ucs_service_profile": 'org-root/org-CPC/ls-CPC-test'
            }
        )
        self.assertEqual('127.0.0.1:org-root/org-CPC/ls-CPC-test',
                         self.driver_info.unique_id_from_node(node))


class FindNodeHandlerTest(base.TestCase):
    def test_found(self):
        test = [('fake', 'fake'),
                ('fake_pxe', 'fake'),
                ('pxe_ipmitool', 'ipmi'),
                ('ipmi', 'ipmi'),
                ('pxe_ilo', 'ilo'),
                ('ilo', 'ilo'),
                ('pxe_drac', 'drac'),
                ('idrac', 'drac'),
                ('pxe_ucs', 'ucs'),
                ('cisco-ucs-managed', 'ucs'),
                ('agent_irmc', 'irmc'),
                ('irmc', 'irmc')]
        for driver, prefix in test:
            handler = nodes._find_node_handler({'pm_type': driver})
            self.assertEqual(prefix, handler._prefix)

    def test_no_driver(self):
        self.assertRaises(exception.InvalidNode,
                          nodes._find_node_handler, {})

    def test_unknown_driver(self):
        self.assertRaises(exception.InvalidNode,
                          nodes._find_node_handler, {'pm_type': 'foobar'})


class NodesTest(base.TestCase):

    def _get_node(self):
        return {'cpu': '1', 'memory': '2048', 'disk': '30', 'arch': 'amd64',
                'mac': ['aaa'], 'pm_addr': 'foo.bar', 'pm_user': 'test',
                'pm_password': 'random', 'pm_type': 'ipmi', 'name': 'node1',
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
        pxe_node_driver_info = {"ipmi_address": "foo.bar",
                                "ipmi_username": "test",
                                "ipmi_password": "random"}
        pxe_node = mock.call(driver="ipmi",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             resource_class='baremetal',
                             properties=node_properties)
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa', physical_network='ctlplane')
        ironic.node.create.assert_has_calls([pxe_node, mock.ANY])
        ironic.port.create.assert_has_calls([port_call])

    def test_register_all_nodes(self):
        node_list = [self._get_node()]
        node_list[0]['root_device'] = {"serial": "abcdef"}
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6",
                           "root_device": {"serial": "abcdef"}}
        ironic = mock.MagicMock()
        nodes.register_all_nodes(node_list, client=ironic)
        pxe_node_driver_info = {"ipmi_address": "foo.bar",
                                "ipmi_username": "test",
                                "ipmi_password": "random"}
        pxe_node = mock.call(driver="ipmi",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             resource_class='baremetal',
                             properties=node_properties)
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa', physical_network='ctlplane')
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
        pxe_node_driver_info = {"ipmi_address": "foo.bar",
                                "ipmi_username": "test",
                                "ipmi_password": "random",
                                "deploy_kernel": "kernel-123",
                                "deploy_ramdisk": "ramdisk-999"}
        pxe_node = mock.call(driver="ipmi",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             resource_class='baremetal',
                             properties=node_properties)
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa', physical_network='ctlplane')
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
        pxe_node_driver_info = {"ipmi_address": "foo.bar",
                                "ipmi_username": "test",
                                "ipmi_password": "random"}
        pxe_node = mock.call(driver="ipmi",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             properties=node_properties,
                             resource_class='baremetal',
                             uuid="abcdef")
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa', physical_network='ctlplane')
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
        pxe_node_driver_info = {"ipmi_address": "foo.bar",
                                "ipmi_username": "test",
                                "ipmi_password": "random"}
        pxe_node = mock.call(driver="ipmi",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             resource_class='baremetal',
                             properties=node_properties)
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa', physical_network='ctlplane')
        ironic.node.create.assert_has_calls([pxe_node, mock.ANY])
        ironic.port.create.assert_has_calls([port_call])

    def test_register_all_nodes_with_interfaces(self):
        interfaces = {'boot_interface': 'pxe',
                      'console_interface': 'ipmitool-socat',
                      'deploy_interface': 'direct',
                      'inspect_interface': 'inspector',
                      'management_interface': 'ipmitool',
                      'network_interface': 'neutron',
                      'power_interface': 'ipmitool',
                      'raid_interface': 'agent',
                      'storage_interface': 'cinder',
                      'vendor_interface': 'ipmitool'}

        node_list = [self._get_node()]
        node_list[0].update(interfaces)
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        ironic = mock.MagicMock()
        nodes.register_all_nodes(node_list, client=ironic)
        pxe_node_driver_info = {"ipmi_address": "foo.bar",
                                "ipmi_username": "test",
                                "ipmi_password": "random"}
        pxe_node = mock.call(driver="ipmi",
                             name='node1',
                             driver_info=pxe_node_driver_info,
                             properties=node_properties,
                             resource_class='baremetal',
                             **interfaces)
        port_call = mock.call(node_uuid=ironic.node.create.return_value.uuid,
                              address='aaa', physical_network='ctlplane')
        ironic.node.create.assert_has_calls([pxe_node, mock.ANY])
        ironic.port.create.assert_has_calls([port_call])

    def test_register_update(self):
        interfaces = {'boot_interface': 'pxe',
                      'console_interface': 'ipmitool-socat',
                      'deploy_interface': 'direct',
                      'inspect_interface': 'inspector',
                      'management_interface': 'ipmitool',
                      'network_interface': 'neutron',
                      'power_interface': 'ipmitool',
                      'raid_interface': 'agent',
                      'storage_interface': 'cinder',
                      'vendor_interface': 'ipmitool'}

        node = self._get_node()
        node.update(interfaces)
        node['root_device'] = {'serial': 'abcdef'}
        ironic = mock.MagicMock()
        node_map = {'mac': {'aaa': 1}}

        def side_effect(*args, **kwargs):
            update_patch = [
                {'path': '/name', 'value': 'node1'},
                {'path': '/driver_info/ipmi_password', 'value': 'random'},
                {'path': '/driver_info/ipmi_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/properties/root_device',
                 'value': {'serial': 'abcdef'}},
                {'path': '/driver_info/ipmi_username', 'value': 'test'}]
            for iface, value in interfaces.items():
                update_patch.append({'path': '/%s' % iface, 'value': value})
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
                {'path': '/driver_info/ipmi_password', 'value': 'random'},
                {'path': '/driver_info/ipmi_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/driver_info/deploy_kernel', 'value': 'image-k'},
                {'path': '/driver_info/deploy_ramdisk', 'value': 'image-r'},
                {'path': '/driver_info/ipmi_username', 'value': 'test'}]
            for key in update_patch:
                key['op'] = 'add'
            self.assertThat(update_patch,
                            matchers.MatchesSetwise(*(map(matchers.Equals,
                                                          args[1]))))
            return mock.Mock(uuid='uuid1')

        ironic.node.update.side_effect = side_effect
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)
        ironic.node.update.assert_called_once_with(1, mock.ANY)

    def test_register_update_with_interfaces(self):
        node = self._get_node()
        ironic = mock.MagicMock()
        node_map = {'mac': {'aaa': 1}}

        def side_effect(*args, **kwargs):
            update_patch = [
                {'path': '/name', 'value': 'node1'},
                {'path': '/driver_info/ipmi_password', 'value': 'random'},
                {'path': '/driver_info/ipmi_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/driver_info/ipmi_username', 'value': 'test'}]
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

    def test_update_node_ironic_ipmi(self):
        self._update_by_type('ipmi')

    def test_update_node_ironic_pxe_ipmitool(self):
        self._update_by_type('pxe_ipmitool')

    def test_update_node_ironic_idrac(self):
        self._update_by_type('idrac')

    def test_update_node_ironic_pxe_drac(self):
        self._update_by_type('pxe_drac')

    def test_update_node_ironic_ilo(self):
        self._update_by_type('ilo')

    def test_update_node_ironic_pxe_ilo(self):
        self._update_by_type('pxe_ilo')

    def test_update_node_ironic_irmc(self):
        self._update_by_type('irmc')

    def test_update_node_ironic_pxe_irmc(self):
        self._update_by_type('pxe_irmc')

    def test_update_node_ironic_redfish(self):
        ironic = mock.MagicMock()
        node_map = {'mac': {}, 'pm_addr': {}}
        node = self._get_node()
        node.update({'pm_type': 'redfish',
                     'pm_system_id': '/path'})
        node_map['pm_addr']['foo.bar/path'] = ironic.node.get.return_value.uuid
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)
        ironic.node.update.assert_called_once_with(
            ironic.node.get.return_value.uuid, mock.ANY)

    def test_update_node_ironic_ovirt(self):
        ironic = mock.MagicMock()
        node_map = {'mac': {}, 'pm_addr': {}}
        node = self._get_node()
        node.update({'pm_type': 'staging-ovirt',
                     'pm_vm_name': 'VM1'})
        node_map['pm_addr']['foo.bar:VM1'] = ironic.node.get.return_value.uuid
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)
        ironic.node.update.assert_called_once_with(
            ironic.node.get.return_value.uuid, mock.ANY)

    def test_register_node_update(self):
        node = self._get_node()
        node['mac'][0] = node['mac'][0].upper()
        ironic = mock.MagicMock()
        node_map = {'mac': {'aaa': 1}}

        def side_effect(*args, **kwargs):
            update_patch = [
                {'path': '/name', 'value': 'node1'},
                {'path': '/driver_info/ipmi_password', 'value': 'random'},
                {'path': '/driver_info/ipmi_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/driver_info/ipmi_username', 'value': 'test'}]
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
                {'path': '/driver_info/ipmi_password', 'value': 'random'},
                {'path': '/driver_info/ipmi_address', 'value': 'foo.bar'},
                {'path': '/properties/memory_mb', 'value': '2048'},
                {'path': '/properties/local_gb', 'value': '30'},
                {'path': '/properties/cpu_arch', 'value': 'amd64'},
                {'path': '/properties/cpus', 'value': '1'},
                {'path': '/properties/capabilities', 'value': 'num_nics:6'},
                {'path': '/driver_info/ipmi_username', 'value': 'test'}]
            for key in update_patch:
                key['op'] = 'add'
            self.assertThat(update_patch,
                            matchers.MatchesSetwise(*(map(matchers.Equals,
                                                          args[1]))))
            return mock.Mock(uuid='abcdef')

        ironic.node.update.side_effect = side_effect
        nodes._update_or_register_ironic_node(node, node_map, client=ironic)
        ironic.node.update.assert_called_once_with('abcdef', mock.ANY)

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
                                                   resource_class='baremetal',
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
            resource_class='baremetal',
            driver_info={'ucs_password': 'random', 'ucs_address': 'foo.bar',
                         'ucs_username': 'test'})

    def test_register_ironic_node_ipmi(self):
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        node = self._get_node()
        node['pm_type'] = 'ipmi'
        node['pm_port'] = '6230'
        client = mock.MagicMock()
        nodes.register_ironic_node(node, client=client)
        client.node.create.assert_called_once_with(
            driver='ipmi', name='node1', properties=node_properties,
            resource_class='baremetal',
            driver_info={'ipmi_password': 'random', 'ipmi_address': 'foo.bar',
                         'ipmi_username': 'test', 'ipmi_port': '6230'})

    def test_register_ironic_node_pxe_ipmitool(self):
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        node = self._get_node()
        node['pm_type'] = 'pxe_ipmitool'
        node['pm_port'] = '6230'
        client = mock.MagicMock()
        nodes.register_ironic_node(node, client=client)
        client.node.create.assert_called_once_with(
            driver='pxe_ipmitool', name='node1', properties=node_properties,
            resource_class='baremetal',
            driver_info={'ipmi_password': 'random', 'ipmi_address': 'foo.bar',
                         'ipmi_username': 'test', 'ipmi_port': '6230'})

    def test_register_ironic_node_idrac(self):
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        node = self._get_node()
        node['pm_type'] = 'idrac'
        node['pm_port'] = '6230'
        client = mock.MagicMock()
        nodes.register_ironic_node(node, client=client)
        client.node.create.assert_called_once_with(
            driver='idrac', name='node1', properties=node_properties,
            resource_class='baremetal',
            driver_info={'drac_password': 'random', 'drac_address': 'foo.bar',
                         'drac_username': 'test', 'drac_port': '6230'})

    def test_register_ironic_node_ilo(self):
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        node = self._get_node()
        node['pm_type'] = 'ilo'
        node['pm_port'] = '1234'
        client = mock.MagicMock()
        nodes.register_ironic_node(node, client=client)
        client.node.create.assert_called_once_with(
            driver='ilo', name='node1', properties=node_properties,
            resource_class='baremetal',
            driver_info={'ilo_password': 'random', 'ilo_address': 'foo.bar',
                         'ilo_username': 'test', 'ilo_port': '1234'})

    def test_register_ironic_node_pxe_drac(self):
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        node = self._get_node()
        node['pm_type'] = 'pxe_drac'
        node['pm_port'] = '6230'
        client = mock.MagicMock()
        nodes.register_ironic_node(node, client=client)
        client.node.create.assert_called_once_with(
            driver='pxe_drac', name='node1', properties=node_properties,
            resource_class='baremetal',
            driver_info={'drac_password': 'random', 'drac_address': 'foo.bar',
                         'drac_username': 'test', 'drac_port': '6230'})

    def test_register_ironic_node_redfish(self):
        node_properties = {"cpus": "1",
                           "memory_mb": "2048",
                           "local_gb": "30",
                           "cpu_arch": "amd64",
                           "capabilities": "num_nics:6"}
        node = self._get_node()
        node['pm_type'] = 'redfish'
        node['pm_system_id'] = '/redfish/v1/Systems/1'
        client = mock.MagicMock()
        nodes.register_ironic_node(node, client=client)
        client.node.create.assert_called_once_with(
            driver='redfish', name='node1', properties=node_properties,
            resource_class='baremetal',
            driver_info={'redfish_password': 'random',
                         'redfish_address': 'foo.bar',
                         'redfish_username': 'test',
                         'redfish_system_id': '/redfish/v1/Systems/1'})

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
        handler = nodes.find_driver_handler('fake_pxe')
        node_map = {'mac': {'aaa': 'abcdef'}, 'pm_addr': {}}
        self.assertEqual('abcdef', nodes._get_node_id(node, handler, node_map))

    def test__get_node_id_conflict(self):
        node = self._get_node()
        handler = nodes.find_driver_handler('pxe_ipmitool')
        node_map = {'mac': {'aaa': 'abcdef'},
                    'pm_addr': {'foo.bar': 'defabc'}}
        self.assertRaises(exception.InvalidNode,
                          nodes._get_node_id,
                          node, handler, node_map)

    def test_get_node_id_valid_duplicate(self):
        node = self._get_node()
        handler = nodes.find_driver_handler('pxe_ipmitool')
        node_map = {'mac': {'aaa': 'id'},
                    'pm_addr': {'foo.bar': 'id'}}
        self.assertEqual('id', nodes._get_node_id(node, handler, node_map))


class TestPopulateNodeMapping(base.TestCase):
    def test_populate_node_mapping_ironic(self):
        client = mock.MagicMock()
        ironic_node = collections.namedtuple('node', ['uuid', 'driver',
                                             'driver_info'])
        ironic_port = collections.namedtuple('port', ['address'])
        node1 = ironic_node('abcdef', 'redfish', {})
        node2 = ironic_node('fedcba', 'pxe_ipmitool',
                            {'ipmi_address': '10.0.1.2'})
        node3 = ironic_node('xyz', 'ipmi', {'ipmi_address': '10.0.1.3'})
        client.node.list_ports.side_effect = ([ironic_port('aaa')], [], [])
        client.node.list.return_value = [node1, node2, node3]
        expected = {'mac': {'aaa': 'abcdef'},
                    'pm_addr': {'10.0.1.2': 'fedcba', '10.0.1.3': 'xyz'},
                    'uuids': {'abcdef', 'fedcba', 'xyz'}}
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


VALID_NODE_JSON = [
    {'_comment': 'This is a comment',
     'pm_type': 'pxe_ipmitool',
     'pm_addr': '192.168.0.1',
     'pm_user': 'root',
     'pm_password': 'p@$$w0rd'},
    {'pm_type': 'ipmi',
     'pm_addr': '192.168.1.1',
     'pm_user': 'root',
     'pm_password': 'p@$$w0rd'},
    {'pm_type': 'pxe_ipmitool',
     'pm_addr': '192.168.0.1',
     'pm_user': 'root',
     'pm_password': 'p@$$w0rd',
     'pm_port': 1234,
     'ipmi_priv_level': 'USER',
     'mac': ['aa:bb:cc:dd:ee:ff',
             '11:22:33:44:55:66'],
     'name': 'foobar1',
     'capabilities': {'foo': 'bar'},
     'kernel_id': 'kernel1',
     'ramdisk_id': 'ramdisk1'},
    {'pm_type': 'ipmi',
     'pm_addr': '192.168.1.1',
     'pm_user': 'root',
     'pm_password': 'p@$$w0rd',
     'pm_port': 1234,
     'ipmi_priv_level': 'USER',
     'mac': ['dd:ee:ff:aa:bb:cc',
             '44:55:66:11:22:33'],
     'name': 'foobar2',
     'capabilities': {'foo': 'bar'},
     'kernel_id': 'kernel1',
     'ramdisk_id': 'ramdisk1'},
    {'pm_type': 'idrac',
     'pm_addr': '1.2.3.4',
     'pm_user': 'root',
     'pm_password': 'p@$$w0rd',
     'mac': ['22:22:22:22:22:22'],
     'capabilities': 'foo:bar,foo1:bar1',
     'cpu': 2,
     'memory': 1024,
     'disk': 40,
     'arch': 'x86_64',
     'root_device': {'foo': 'bar'}},
    {'pm_type': 'redfish',
     'pm_addr': '1.2.3.4',
     'pm_user': 'root',
     'pm_password': 'foobar',
     'pm_system_id': '/redfish/v1/Systems/1'},
]


class TestValidateNodes(base.TestCase):
    def test_valid(self):
        nodes.validate_nodes(VALID_NODE_JSON)

    def test_unknown_driver(self):
        nodes_json = [
            {'pm_type': 'pxe_foobar',
             'pm_addr': '1.1.1.1',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd'},
        ]
        self.assertRaisesRegex(exception.InvalidNode,
                               'unknown pm_type .* pxe_foobar',
                               nodes.validate_nodes, nodes_json)

    def test_duplicate_ipmi_address(self):
        nodes_json = [
            {'pm_type': 'pxe_ipmitool',
             'pm_addr': '1.1.1.1',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd'},
            {'pm_type': 'ipmi',
             'pm_addr': '1.1.1.1',
             'pm_user': 'user',
             'pm_password': 'p@$$w0rd'},
        ]
        self.assertRaisesRegex(exception.InvalidNode,
                               'Node identified by 1.1.1.1 is already present',
                               nodes.validate_nodes, nodes_json)

    def test_invalid_mac(self):
        nodes_json = [
            {'pm_type': 'pxe_ipmitool',
             'pm_addr': '1.1.1.1',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd',
             'mac': ['42']},
        ]
        self.assertRaisesRegex(exception.InvalidNode,
                               'MAC address 42 is invalid',
                               nodes.validate_nodes, nodes_json)

    def test_duplicate_mac(self):
        nodes_json = [
            {'pm_type': 'pxe_ipmitool',
             'pm_addr': '1.1.1.1',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd',
             'mac': ['11:22:33:44:55:66']},
            {'pm_type': 'ipmi',
             'pm_addr': '1.2.1.1',
             'pm_user': 'user',
             'pm_password': 'p@$$w0rd',
             'mac': ['11:22:33:44:55:66']},
        ]
        self.assertRaisesRegex(exception.InvalidNode,
                               'MAC 11:22:33:44:55:66 is not unique',
                               nodes.validate_nodes, nodes_json)

    def test_duplicate_names(self):
        nodes_json = [
            {'pm_type': 'pxe_ipmitool',
             'pm_addr': '1.1.1.1',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd',
             'name': 'name'},
            {'pm_type': 'pxe_ipmitool',
             'pm_addr': '1.2.1.2',
             'pm_user': 'user',
             'pm_password': 'p@$$w0rd',
             'name': 'name'},
        ]
        self.assertRaisesRegex(exception.InvalidNode,
                               'Name "name" is not unique',
                               nodes.validate_nodes, nodes_json)

    def test_invalid_capability(self):
        nodes_json = [
            {'pm_type': 'pxe_ipmitool',
             'pm_addr': '1.1.1.1',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd',
             'capabilities': '42'},
        ]
        self.assertRaisesRegex(exception.InvalidNode,
                               'Invalid capabilities: 42',
                               nodes.validate_nodes, nodes_json)

    def test_unexpected_fields(self):
        nodes_json = [
            {'pm_type': 'pxe_ipmitool',
             'pm_addr': '1.1.1.1',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd',
             'pm_foobar': '42'},
        ]
        self.assertRaisesRegex(exception.InvalidNode,
                               'Unknown field pm_foobar',
                               nodes.validate_nodes, nodes_json)

    def test_missing_fields(self):
        for field in ('pm_addr', 'pm_user', 'pm_password'):
            nodes_json = [
                {'pm_type': 'pxe_ipmitool',
                 'pm_addr': '1.1.1.1',
                 'pm_user': 'root',
                 'pm_password': 'p@$$w0rd'},
            ]
            del nodes_json[0][field]

            self.assertRaisesRegex(exception.InvalidNode,
                                   'fields are missing: %s' % field,
                                   nodes.validate_nodes, nodes_json)

    def test_duplicate_redfish_node(self):
        nodes_json = [
            {'pm_type': 'redfish',
             'pm_addr': 'example.com',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd',
             'pm_system_id': '/redfish/v1/Systems/1'},
            {'pm_type': 'redfish',
             'pm_addr': 'https://example.com',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd',
             'pm_system_id': '/redfish/v1/Systems/1'},
        ]
        self.assertRaisesRegex(
            exception.InvalidNode,
            'Node identified by example.com/redfish/v1/Systems/1 '
            'is already present',
            nodes.validate_nodes, nodes_json)

    def test_redfish_missing_system_id(self):
        nodes_json = [
            {'pm_type': 'redfish',
             'pm_addr': '1.1.1.1',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd'},
        ]

        self.assertRaisesRegex(exception.InvalidNode,
                               'fields are missing: pm_system_id',
                               nodes.validate_nodes, nodes_json)

    def test_invalid_root_device(self):
        nodes_json = [
            {'pm_type': 'pxe_ipmitool',
             'pm_addr': '1.1.1.1',
             'pm_user': 'root',
             'pm_password': 'p@$$w0rd',
             'root_device': 42}
        ]
        self.assertRaisesRegex(exception.InvalidNode,
                               'Invalid root device',
                               nodes.validate_nodes, nodes_json)
