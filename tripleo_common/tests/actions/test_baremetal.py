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

from glanceclient import exc as glance_exceptions
import ironic_inspector_client
from oslo_concurrency import processutils
from oslo_utils import units

from tripleo_common.actions import baremetal
from tripleo_common import exception
from tripleo_common.tests import base


class TestConfigureBootAction(base.TestCase):

    def setUp(self):
        super(TestConfigureBootAction, self).setUp()
        self.node_update = [{'op': 'add',
                             'path': '/properties/capabilities',
                             'value': 'boot_option:local'},
                            {'op': 'add',
                             'path': '/driver_info/deploy_ramdisk',
                             'value': 'r_id'},
                            {'op': 'add',
                             'path': '/driver_info/deploy_kernel',
                             'value': 'k_id'},
                            {'op': 'add',
                             'path': '/driver_info/rescue_ramdisk',
                             'value': 'r_id'},
                            {'op': 'add',
                             'path': '/driver_info/rescue_kernel',
                             'value': 'k_id'}]

        self.ironic = mock.MagicMock()
        ironic_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_baremetal_client',
            return_value=self.ironic)
        self.mock_ironic = ironic_patcher.start()
        self.addCleanup(ironic_patcher.stop)

        self.glance = mock.MagicMock()
        glance_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_image_client',
            return_value=self.glance)
        self.mock_glance = glance_patcher.start()
        self.addCleanup(glance_patcher.stop)

        def mock_find(name, disk_format):
            if name == 'bm-deploy-kernel':
                return mock.MagicMock(id='k_id')
            elif name == 'bm-deploy-ramdisk':
                return mock.MagicMock(id='r_id')
        self.glance.images.find = mock_find
        self.context = mock.MagicMock()

    def test_run_instance_boot_option(self):
        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID',
                                               instance_boot_option='netboot')
        result = action.run(self.context)
        self.assertIsNone(result)

        self.node_update[0].update({'value': 'boot_option:netboot'})
        self.ironic.node.update.assert_called_once_with(mock.ANY,
                                                        self.node_update)

    def test_run_instance_boot_option_not_set(self):
        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID')
        result = action.run(self.context)
        self.assertIsNone(result)

        self.node_update[0].update({'value': ''})
        self.ironic.node.update.assert_called_once_with(mock.ANY,
                                                        self.node_update)

    def test_run_instance_boot_option_already_set_no_overwrite(self):
        node_mock = mock.MagicMock()
        node_mock.properties.get.return_value = ({'boot_option': 'netboot'})
        self.ironic.node.get.return_value = node_mock

        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID')
        result = action.run(self.context)
        self.assertIsNone(result)

        self.node_update[0].update({'value': 'boot_option:netboot'})
        self.ironic.node.update.assert_called_once_with(mock.ANY,
                                                        self.node_update)

    def test_run_instance_boot_option_already_set_do_overwrite(self):
        node_mock = mock.MagicMock()
        node_mock.properties.get.return_value = ({'boot_option': 'netboot'})
        self.ironic.node.get.return_value = node_mock

        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID',
                                               instance_boot_option='local')
        result = action.run(self.context)
        self.assertIsNone(result)

        self.node_update[0].update({'value': 'boot_option:local'})
        self.ironic.node.update.assert_called_once_with(mock.ANY,
                                                        self.node_update)

    def test_run_new_kernel_and_ram_image(self):
        image_ids = {'kernel': 'test_kernel_id', 'ramdisk': 'test_ramdisk_id'}

        with mock.patch('tripleo_common.utils.glance.create_or_find_kernel_and'
                        '_ramdisk') as mock_find:
            mock_find.return_value = image_ids
            action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID',
                                                   kernel_name='test_kernel',
                                                   ramdisk_name='test_ramdisk')
            result = action.run(self.context)

        self.assertIsNone(result)

        self.node_update[0].update({'value': ''})
        self.node_update[1:] = [{'op': 'add',
                                 'path': '/driver_info/deploy_ramdisk',
                                 'value': 'test_ramdisk_id'},
                                {'op': 'add',
                                 'path': '/driver_info/deploy_kernel',
                                 'value': 'test_kernel_id'},
                                {'op': 'add',
                                 'path': '/driver_info/rescue_ramdisk',
                                 'value': 'test_ramdisk_id'},
                                {'op': 'add',
                                 'path': '/driver_info/rescue_kernel',
                                 'value': 'test_kernel_id'}]
        self.ironic.node.update.assert_called_once_with(mock.ANY,
                                                        self.node_update)

    def test_run_glance_ids_not_found(self):
        self.glance.images.find = mock.Mock(
            side_effect=glance_exceptions.NotFound)

        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID',
                                               kernel_name='unknown_kernel',
                                               ramdisk_name='unknown_ramdisk')
        result = action.run(self.context)
        self.assertIn("not found", str(result.error))

    def test_run_exception_on_node_update(self):
        self.ironic.node.update.side_effect = Exception("Update error")

        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID')
        result = action.run(self.context)

        self.assertIn("Update error", str(result.error))


class TestConfigureRootDeviceAction(base.TestCase):

    def setUp(self):
        super(TestConfigureRootDeviceAction, self).setUp()

        # Mock data
        self.disks = [
            {'name': '/dev/sda', 'size': 11 * units.Gi},
            {'name': '/dev/sdb', 'size': 2 * units.Gi},
            {'name': '/dev/sdc', 'size': 5 * units.Gi},
            {'name': '/dev/sdd', 'size': 21 * units.Gi},
            {'name': '/dev/sde', 'size': 13 * units.Gi},
        ]
        for i, disk in enumerate(self.disks):
            disk['wwn'] = 'wwn%d' % i
            disk['serial'] = 'serial%d' % i

        # Ironic mocks
        self.ironic = mock.MagicMock()
        ironic_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_baremetal_client',
            return_value=self.ironic)
        self.mock_ironic = ironic_patcher.start()
        self.addCleanup(ironic_patcher.stop)

        self.ironic.node.list.return_value = [
            mock.Mock(uuid="ABCDEFGH"),
        ]

        self.node = mock.Mock(uuid="ABCDEFGH", properties={})
        self.ironic.node.get.return_value = self.node

        # inspector mocks
        self.inspector = mock.MagicMock()
        inspector_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.'
            'get_baremetal_introspection_client',
            return_value=self.inspector)
        self.mock_inspector = inspector_patcher.start()
        self.addCleanup(inspector_patcher.stop)

        self.inspector.get_data.return_value = {
            'inventory': {'disks': self.disks}
        }
        self.context = mock.MagicMock()

    def test_smallest(self):
        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        action.run(self.context)

        self.assertEqual(self.ironic.node.update.call_count, 1)
        root_device_args = self.ironic.node.update.call_args_list[0]
        expected_patch = [{'op': 'add', 'path': '/properties/root_device',
                           'value': {'wwn': 'wwn2'}},
                          {'op': 'add', 'path': '/properties/local_gb',
                           'value': 4}]
        self.assertEqual(mock.call('ABCDEFGH', expected_patch),
                         root_device_args)

    def test_smallest_with_ext(self):
        self.disks[2]['wwn_with_extension'] = 'wwnext'
        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        action.run(self.context)

        self.assertEqual(self.ironic.node.update.call_count, 1)
        root_device_args = self.ironic.node.update.call_args_list[0]
        expected_patch = [{'op': 'add', 'path': '/properties/root_device',
                           'value': {'wwn_with_extension': 'wwnext'}},
                          {'op': 'add', 'path': '/properties/local_gb',
                           'value': 4}]
        self.assertEqual(mock.call('ABCDEFGH', expected_patch),
                         root_device_args)

    def test_largest(self):
        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='largest')
        action.run(self.context)

        self.assertEqual(self.ironic.node.update.call_count, 1)
        root_device_args = self.ironic.node.update.call_args_list[0]
        expected_patch = [{'op': 'add', 'path': '/properties/root_device',
                           'value': {'wwn': 'wwn3'}},
                          {'op': 'add', 'path': '/properties/local_gb',
                           'value': 20}]
        self.assertEqual(mock.call('ABCDEFGH', expected_patch),
                         root_device_args)

    def test_largest_with_ext(self):
        self.disks[3]['wwn_with_extension'] = 'wwnext'
        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='largest')
        action.run(self.context)

        self.assertEqual(self.ironic.node.update.call_count, 1)
        root_device_args = self.ironic.node.update.call_args_list[0]
        expected_patch = [{'op': 'add', 'path': '/properties/root_device',
                           'value': {'wwn_with_extension': 'wwnext'}},
                          {'op': 'add', 'path': '/properties/local_gb',
                           'value': 20}]
        self.assertEqual(mock.call('ABCDEFGH', expected_patch),
                         root_device_args)

    def test_no_overwrite(self):
        self.node.properties['root_device'] = {'foo': 'bar'}

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        action.run(self.context)

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_with_overwrite(self):
        self.node.properties['root_device'] = {'foo': 'bar'}

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest',
                                                     overwrite=True)
        action.run(self.context)

        self.assertEqual(self.ironic.node.update.call_count, 1)
        root_device_args = self.ironic.node.update.call_args_list[0]
        expected_patch = [{'op': 'add', 'path': '/properties/root_device',
                           'value': {'wwn': 'wwn2'}},
                          {'op': 'add', 'path': '/properties/local_gb',
                           'value': 4}]
        self.assertEqual(mock.call('ABCDEFGH', expected_patch),
                         root_device_args)

    def test_minimum_size(self):
        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest',
                                                     minimum_size=10)
        action.run(self.context)

        self.assertEqual(self.ironic.node.update.call_count, 1)
        root_device_args = self.ironic.node.update.call_args_list[0]
        expected_patch = [{'op': 'add', 'path': '/properties/root_device',
                           'value': {'wwn': 'wwn0'}},
                          {'op': 'add', 'path': '/properties/local_gb',
                           'value': 10}]
        self.assertEqual(mock.call('ABCDEFGH', expected_patch),
                         root_device_args)

    def test_bad_inventory(self):
        self.inspector.get_data.return_value = {}

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        self.assertRaisesRegex(exception.RootDeviceDetectionError,
                               "Malformed introspection data",
                               action.run,
                               self.context)

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_no_disks(self):
        self.inspector.get_data.return_value = {
            'inventory': {
                'disks': [{'name': '/dev/sda', 'size': 1 * units.Gi}]
            }
        }

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        self.assertRaisesRegex(exception.RootDeviceDetectionError,
                               "No suitable disks",
                               action.run,
                               self.context)

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_no_data(self):
        self.inspector.get_data.side_effect = (
            ironic_inspector_client.ClientError(mock.Mock()))

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        self.assertRaisesRegex(exception.RootDeviceDetectionError,
                               "No introspection data",
                               action.run,
                               self.context)

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_no_wwn_and_serial(self):
        self.inspector.get_data.return_value = {
            'inventory': {
                'disks': [{'name': '/dev/sda', 'size': 10 * units.Gi}]
                }
        }

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        self.assertRaisesRegex(exception.RootDeviceDetectionError,
                               "Neither WWN nor serial number are known",
                               action.run,
                               self.context)

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_device_list(self):
        action = baremetal.ConfigureRootDeviceAction(
            node_uuid='MOCK_UUID',
            root_device='hda,sda,sdb,sdc')
        action.run(self.context)

        self.assertEqual(self.ironic.node.update.call_count, 1)
        root_device_args = self.ironic.node.update.call_args_list[0]
        expected_patch = [{'op': 'add', 'path': '/properties/root_device',
                           'value': {'wwn': 'wwn0'}},
                          {'op': 'add', 'path': '/properties/local_gb',
                           'value': 10}]
        self.assertEqual(mock.call('ABCDEFGH', expected_patch),
                         root_device_args)

    def test_device_list_not_found(self):
        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='hda')

        self.assertRaisesRegex(exception.RootDeviceDetectionError,
                               "Cannot find a disk",
                               action.run,
                               self.context)
        self.assertEqual(self.ironic.node.update.call_count, 0)


class TestCellV2DiscoverHostsAction(base.TestCase):

    @mock.patch('tripleo_common.utils.nodes.run_nova_cell_v2_discovery')
    def test_run(self, mock_command):
        action = baremetal.CellV2DiscoverHostsAction()
        action.run(mock.MagicMock())
        mock_command.assert_called_once()

    @mock.patch('tripleo_common.utils.nodes.run_nova_cell_v2_discovery')
    def test_failure(self, mock_command):
        mock_command.side_effect = processutils.ProcessExecutionError(
            exit_code=1,
            stdout='captured stdout',
            stderr='captured stderr',
            cmd='command'
        )
        action = baremetal.CellV2DiscoverHostsAction()
        result = action.run(mock.MagicMock())
        self.assertTrue(result.is_error())
        mock_command.assert_called_once()


class TestGetProfileAction(base.TestCase):

    def test_run(self):
        mock_ctx = mock.MagicMock()
        node = {
            'uuid': 'abcd1',
            'properties': {
                'capabilities': 'profile:compute'
            }
        }
        action = baremetal.GetProfileAction(node=node)
        result = action.run(mock_ctx)
        expected_result = {
            'uuid': 'abcd1',
            'profile': 'compute'
        }
        self.assertEqual(expected_result, result)


class TestGetNodeHintAction(base.TestCase):

    def test_run(self):
        mock_ctx = mock.MagicMock()
        node = {
            'uuid': 'abcd1',
            'properties': {
                'capabilities': 'profile:compute,node:compute-0'
            }
        }
        action = baremetal.GetNodeHintAction(node=node)
        result = action.run(mock_ctx)
        expected_result = {
            'uuid': 'abcd1',
            'hint': 'compute-0'
        }
        self.assertEqual(expected_result, result)


@mock.patch.object(baremetal.socket, 'gethostbyname', lambda x: x)
class TestGetCandidateNodes(base.TestCase):
    def setUp(self):
        super(TestGetCandidateNodes, self).setUp()
        self.existing_nodes = [
            {'uuid': '1', 'driver': 'ipmi',
             'driver_info': {'ipmi_address': '10.0.0.1'}},
            {'uuid': '2', 'driver': 'pxe_ipmitool',
             'driver_info': {'ipmi_address': '10.0.0.1', 'ipmi_port': 6235}},
            {'uuid': '3', 'driver': 'foobar', 'driver_info': {}},
            {'uuid': '4', 'driver': 'fake',
             'driver_info': {'fake_address': 42}},
            {'uuid': '5', 'driver': 'ipmi', 'driver_info': {}},
            {'uuid': '6', 'driver': 'pxe_drac',
             'driver_info': {'drac_address': '10.0.0.2'}},
            {'uuid': '7', 'driver': 'pxe_drac',
             'driver_info': {'drac_address': '10.0.0.3', 'drac_port': 6230}},
        ]

    def test_existing_ips(self):
        action = baremetal.GetCandidateNodes([], [], [], self.existing_nodes)
        result = action._existing_ips()

        self.assertEqual({('10.0.0.1', 623), ('10.0.0.1', 6235),
                          ('10.0.0.2', None), ('10.0.0.3', 6230)},
                         set(result))

    def test_with_list(self):
        action = baremetal.GetCandidateNodes(
            ['10.0.0.1', '10.0.0.2', '10.0.0.3'],
            [623, 6230, 6235],
            [['admin', 'password'], ['admin', 'admin']],
            self.existing_nodes)
        result = action.run(mock.Mock())

        self.assertEqual([
            {'ip': '10.0.0.3', 'port': 623,
             'username': 'admin', 'password': 'password'},
            {'ip': '10.0.0.1', 'port': 6230,
             'username': 'admin', 'password': 'password'},
            {'ip': '10.0.0.3', 'port': 6235,
             'username': 'admin', 'password': 'password'},
            {'ip': '10.0.0.3', 'port': 623,
             'username': 'admin', 'password': 'admin'},
            {'ip': '10.0.0.1', 'port': 6230,
             'username': 'admin', 'password': 'admin'},
            {'ip': '10.0.0.3', 'port': 6235,
             'username': 'admin', 'password': 'admin'},
        ], result)

    def test_with_subnet(self):
        action = baremetal.GetCandidateNodes(
            '10.0.0.0/30',
            [623, 6230, 6235],
            [['admin', 'password'], ['admin', 'admin']],
            self.existing_nodes)
        result = action.run(mock.Mock())

        self.assertEqual([
            {'ip': '10.0.0.1', 'port': 6230,
             'username': 'admin', 'password': 'password'},
            {'ip': '10.0.0.1', 'port': 6230,
             'username': 'admin', 'password': 'admin'},
        ], result)

    def test_invalid_subnet(self):
        action = baremetal.GetCandidateNodes(
            'meow',
            [623, 6230, 6235],
            [['admin', 'password'], ['admin', 'admin']],
            self.existing_nodes)
        result = action.run(mock.Mock())
        self.assertTrue(result.is_error())


@mock.patch.object(processutils, 'execute', autospec=True)
class TestProbeNode(base.TestCase):
    action = baremetal.ProbeNode('10.0.0.42', 623, 'admin', 'password')

    def test_success(self, mock_execute):
        result = self.action.run(mock.Mock())
        self.assertEqual({'pm_type': 'ipmi',
                          'pm_addr': '10.0.0.42',
                          'pm_user': 'admin',
                          'pm_password': 'password',
                          'pm_port': 623},
                         result)
        mock_execute.assert_called_once_with('ipmitool', '-I', 'lanplus',
                                             '-H', '10.0.0.42',
                                             '-L', 'ADMINISTRATOR',
                                             '-p', '623', '-U', 'admin',
                                             '-f', mock.ANY, 'power', 'status',
                                             attempts=2)

    def test_failure(self, mock_execute):
        mock_execute.side_effect = processutils.ProcessExecutionError()
        self.assertIsNone(self.action.run(mock.Mock()))
        mock_execute.assert_called_once_with('ipmitool', '-I', 'lanplus',
                                             '-H', '10.0.0.42',
                                             '-L', 'ADMINISTRATOR',
                                             '-p', '623', '-U', 'admin',
                                             '-f', mock.ANY, 'power', 'status',
                                             attempts=2)
