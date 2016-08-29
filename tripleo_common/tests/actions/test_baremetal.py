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

from tripleo_common.actions import baremetal
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
        self.addCleanup(self.mock_ironic.stop)

        self.glance = mock.MagicMock()
        glance_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction._get_image_client',
            return_value=self.glance)
        self.mock_glance = glance_patcher.start()
        self.addCleanup(self.mock_glance.stop)

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
