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
                             'value': 'k_id'}]

        self.ironic = mock.MagicMock()
        ironic_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction._get_baremetal_client',
            return_value=self.ironic)
        self.mock_ironic = ironic_patcher.start()
        self.addCleanup(ironic_patcher.stop)

        self.glance = mock.MagicMock()
        glance_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction._get_image_client',
            return_value=self.glance)
        self.mock_glance = glance_patcher.start()
        self.addCleanup(glance_patcher.stop)

        def mock_find(name, disk_format):
            if name == 'bm-deploy-kernel':
                return mock.MagicMock(id='k_id')
            elif name == 'bm-deploy-ramdisk':
                return mock.MagicMock(id='r_id')
        self.glance.images.find = mock_find

    def test_run_instance_boot_option(self):
        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID',
                                               instance_boot_option='netboot')
        result = action.run()
        self.assertEqual(result, None)

        self.node_update[0].update({'value': 'boot_option:netboot'})
        self.ironic.node.update.assert_called_once_with(mock.ANY,
                                                        self.node_update)

    def test_run_instance_boot_option_not_set(self):
        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID')
        result = action.run()
        self.assertEqual(result, None)

        self.node_update[0].update({'value': 'boot_option:local'})
        self.ironic.node.update.assert_called_once_with(mock.ANY,
                                                        self.node_update)

    def test_run_instance_boot_option_already_set_no_overwrite(self):
        node_mock = mock.MagicMock()
        node_mock.properties.get.return_value = ({'boot_option': 'netboot'})
        self.ironic.node.get.return_value = node_mock

        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID')
        result = action.run()
        self.assertEqual(result, None)

        self.node_update[0].update({'value': 'boot_option:netboot'})
        self.ironic.node.update.assert_called_once_with(mock.ANY,
                                                        self.node_update)

    def test_run_instance_boot_option_already_set_do_overwrite(self):
        node_mock = mock.MagicMock()
        node_mock.properties.get.return_value = ({'boot_option': 'netboot'})
        self.ironic.node.get.return_value = node_mock

        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID',
                                               instance_boot_option='local')
        result = action.run()
        self.assertEqual(result, None)

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
            result = action.run()

        self.assertEqual(result, None)

        self.node_update[1].update({'value': 'test_ramdisk_id'})
        self.node_update[2].update({'value': 'test_kernel_id'})
        self.ironic.node.update.assert_called_once_with(mock.ANY,
                                                        self.node_update)

    def test_run_glance_ids_not_found(self):
        self.glance.images.find = mock.Mock(
            side_effect=glance_exceptions.NotFound)

        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID',
                                               kernel_name='unknown_kernel',
                                               ramdisk_name='unknown_ramdisk')
        result = action.run()
        self.assertIn("not found", str(result.error))

    def test_run_exception_on_node_update(self):
        self.ironic.node.update.side_effect = Exception("Update error")

        action = baremetal.ConfigureBootAction(node_uuid='MOCK_UUID')
        result = action.run()

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
            'tripleo_common.actions.base.TripleOAction._get_baremetal_client',
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
            '_get_baremetal_introspection_client',
            return_value=self.inspector)
        self.mock_inspector = inspector_patcher.start()
        self.addCleanup(inspector_patcher.stop)

        self.inspector.get_data.return_value = {
            'inventory': {'disks': self.disks}
        }

    def test_smallest(self):
        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        action.run()

        self.assertEqual(self.ironic.node.update.call_count, 1)
        root_device_args = self.ironic.node.update.call_args_list[0]
        expected_patch = [{'op': 'add', 'path': '/properties/root_device',
                           'value': {'wwn': 'wwn2'}},
                          {'op': 'add', 'path': '/properties/local_gb',
                           'value': 4}]
        self.assertEqual(mock.call('ABCDEFGH', expected_patch),
                         root_device_args)

    def test_largest(self):
        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='largest')
        action.run()

        self.assertEqual(self.ironic.node.update.call_count, 1)
        root_device_args = self.ironic.node.update.call_args_list[0]
        expected_patch = [{'op': 'add', 'path': '/properties/root_device',
                           'value': {'wwn': 'wwn3'}},
                          {'op': 'add', 'path': '/properties/local_gb',
                           'value': 20}]
        self.assertEqual(mock.call('ABCDEFGH', expected_patch),
                         root_device_args)

    def test_no_overwrite(self):
        self.node.properties['root_device'] = {'foo': 'bar'}

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        action.run()

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_with_overwrite(self):
        self.node.properties['root_device'] = {'foo': 'bar'}

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest',
                                                     overwrite=True)
        action.run()

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
        action.run()

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
        self.assertRaisesRegexp(exception.RootDeviceDetectionError,
                                "Malformed introspection data",
                                action.run)

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_no_disks(self):
        self.inspector.get_data.return_value = {
            'inventory': {
                'disks': [{'name': '/dev/sda', 'size': 1 * units.Gi}]
            }
        }

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        self.assertRaisesRegexp(exception.RootDeviceDetectionError,
                                "No suitable disks",
                                action.run)

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_no_data(self):
        self.inspector.get_data.side_effect = (
            ironic_inspector_client.ClientError(mock.Mock()))

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        self.assertRaisesRegexp(exception.RootDeviceDetectionError,
                                "No introspection data",
                                action.run)

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_no_wwn_and_serial(self):
        self.inspector.get_data.return_value = {
            'inventory': {
                'disks': [{'name': '/dev/sda', 'size': 10 * units.Gi}]
                }
        }

        action = baremetal.ConfigureRootDeviceAction(node_uuid='MOCK_UUID',
                                                     root_device='smallest')
        self.assertRaisesRegexp(exception.RootDeviceDetectionError,
                                "Neither WWN nor serial number are known",
                                action.run)

        self.assertEqual(self.ironic.node.update.call_count, 0)

    def test_device_list(self):
        action = baremetal.ConfigureRootDeviceAction(
            node_uuid='MOCK_UUID',
            root_device='hda,sda,sdb,sdc')
        action.run()

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

        self.assertRaisesRegexp(exception.RootDeviceDetectionError,
                                "Cannot find a disk",
                                action.run)
        self.assertEqual(self.ironic.node.update.call_count, 0)
