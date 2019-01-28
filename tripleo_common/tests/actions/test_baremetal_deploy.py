# Copyright 2018 Red Hat, Inc.
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

import metalsmith
from metalsmith import sources
import mock
from openstack import exceptions as sdk_exc

from tripleo_common.actions import baremetal_deploy
from tripleo_common.tests import base


@mock.patch.object(baremetal_deploy, '_provisioner', autospec=True)
class TestReserveNodes(base.TestCase):

    def test_success(self, mock_pr):
        instances = [
            {'hostname': 'host1', 'profile': 'compute'},
            {'hostname': 'host2', 'resource_class': 'compute',
             'capabilities': {'answer': '42'}},
            {'name': 'control-0', 'traits': ['CUSTOM_GPU']},
        ]
        action = baremetal_deploy.ReserveNodesAction(instances)
        result = action.run(mock.Mock())

        self.assertEqual(
            [{'node': mock_pr.return_value.reserve_node.return_value.id,
              'instance': req} for req in instances],
            result['reservations'])
        mock_pr.return_value.reserve_node.assert_has_calls([
            mock.call(resource_class='baremetal', traits=None,
                      capabilities={'profile': 'compute'}, candidates=None),
            mock.call(resource_class='compute', traits=None,
                      capabilities={'answer': '42'}, candidates=None),
            mock.call(resource_class='baremetal', traits=['CUSTOM_GPU'],
                      capabilities=None, candidates=['control-0']),
        ])
        self.assertFalse(mock_pr.return_value.unprovision_node.called)

    def test_missing_hostname(self, mock_pr):
        instances = [
            {'hostname': 'host1'},
            {'resource_class': 'compute', 'capabilities': {'answer': '42'}}
        ]
        action = baremetal_deploy.ReserveNodesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn("'hostname' is a required property", result.error)
        self.assertFalse(mock_pr.return_value.reserve_node.called)
        self.assertFalse(mock_pr.return_value.unprovision_node.called)

    @mock.patch.object(baremetal_deploy.LOG, 'exception', autospec=True)
    def test_failure(self, mock_log, mock_pr):
        instances = [
            {'hostname': 'host1'},
            {'hostname': 'host2', 'resource_class': 'compute',
             'capabilities': {'answer': '42'}},
            {'hostname': 'host3'},
        ]
        success_node = mock.Mock(uuid='uuid1')
        mock_pr.return_value.reserve_node.side_effect = [
            success_node,
            RuntimeError("boom"),
        ]
        action = baremetal_deploy.ReserveNodesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn('RuntimeError: boom', result.error)
        mock_pr.return_value.reserve_node.assert_has_calls([
            mock.call(resource_class='baremetal', capabilities=None,
                      candidates=None, traits=None),
            mock.call(resource_class='compute', capabilities={'answer': '42'},
                      candidates=None, traits=None)
        ])
        mock_pr.return_value.unprovision_node.assert_called_once_with(
            success_node)
        mock_log.assert_called_once_with('Provisioning failed, cleaning up')

    @mock.patch.object(baremetal_deploy.LOG, 'exception', autospec=True)
    def test_failure_to_clean_up(self, mock_log, mock_pr):
        instances = [
            {'hostname': 'host1'},
            {'hostname': 'host2', 'resource_class': 'compute',
             'capabilities': {'answer': '42'}},
            {'hostname': 'host3'},
        ]
        success_node = mock.Mock(uuid='uuid1')
        mock_pr.return_value.reserve_node.side_effect = [
            success_node,
            RuntimeError("boom"),
        ]
        mock_pr.return_value.unprovision_node.side_effect = AssertionError
        action = baremetal_deploy.ReserveNodesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn('RuntimeError: boom', result.error)
        mock_pr.return_value.reserve_node.assert_has_calls([
            mock.call(resource_class='baremetal', capabilities=None,
                      candidates=None, traits=None),
            mock.call(resource_class='compute', capabilities={'answer': '42'},
                      candidates=None, traits=None)
        ])
        mock_pr.return_value.unprovision_node.assert_called_once_with(
            success_node)
        mock_log.assert_has_calls([
            mock.call('Provisioning failed, cleaning up'),
            mock.call('Unable to release node %s, moving on', success_node)
        ])

    def test_duplicate_hostname(self, mock_pr):
        instances = [
            {'hostname': 'host1'},
            # name is used as the default for hostname
            {'name': 'host1'},
        ]
        action = baremetal_deploy.ReserveNodesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn('Hostname host1 is used more than once', result.error)
        self.assertFalse(mock_pr.return_value.reserve_node.called)

    def test_duplicate_name(self, mock_pr):
        instances = [
            {'hostname': 'host1', 'name': 'node-1'},
            # name is used as the default for hostname
            {'name': 'node-1'},
        ]
        action = baremetal_deploy.ReserveNodesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn('Node node-1 is requested more than once', result.error)
        self.assertFalse(mock_pr.return_value.reserve_node.called)


@mock.patch.object(baremetal_deploy, '_provisioner', autospec=True)
class TestDeployNode(base.TestCase):

    def test_success_defaults(self, mock_pr):
        action = baremetal_deploy.DeployNodeAction(
            instance={'hostname': 'host1'},
            node='1234'
        )
        result = action.run(mock.Mock())

        pr = mock_pr.return_value
        self.assertEqual(
            pr.provision_node.return_value.to_dict.return_value,
            result)
        pr.provision_node.assert_called_once_with(
            '1234',
            image=mock.ANY,
            nics=[{'network': 'ctlplane'}],
            hostname='host1',
            root_size_gb=49,
            swap_size_mb=None,
            config=mock.ANY,
        )
        config = pr.provision_node.call_args[1]['config']
        self.assertEqual([], config.ssh_keys)
        self.assertEqual('heat-admin', config.users[0]['name'])
        source = pr.provision_node.call_args[1]['image']
        self.assertIsInstance(source, sources.GlanceImage)
        # TODO(dtantsur): check the image when it's a public field

    def test_success_with_name(self, mock_pr):
        action = baremetal_deploy.DeployNodeAction(
            instance={'name': 'host1'},
            node='1234'
        )
        result = action.run(mock.Mock())

        pr = mock_pr.return_value
        self.assertEqual(
            pr.provision_node.return_value.to_dict.return_value,
            result)
        pr.provision_node.assert_called_once_with(
            '1234',
            image=mock.ANY,
            nics=[{'network': 'ctlplane'}],
            hostname='host1',
            root_size_gb=49,
            swap_size_mb=None,
            config=mock.ANY,
        )
        config = pr.provision_node.call_args[1]['config']
        self.assertEqual([], config.ssh_keys)
        self.assertEqual('heat-admin', config.users[0]['name'])

    def test_success_advanced_nic(self, mock_pr):
        action = baremetal_deploy.DeployNodeAction(
            instance={'hostname': 'host1',
                      'nics': [{'subnet': 'ctlplane-subnet'},
                               {'network': 'ctlplane',
                                'fixed_ip': '10.0.0.2'}]},
            node='1234'
        )
        result = action.run(mock.Mock())

        pr = mock_pr.return_value
        self.assertEqual(
            pr.provision_node.return_value.to_dict.return_value,
            result)
        pr.provision_node.assert_called_once_with(
            '1234',
            image=mock.ANY,
            nics=[{'subnet': 'ctlplane-subnet'},
                  {'network': 'ctlplane', 'fixed_ip': '10.0.0.2'}],
            hostname='host1',
            root_size_gb=49,
            swap_size_mb=None,
            config=mock.ANY,
        )
        config = pr.provision_node.call_args[1]['config']
        self.assertEqual([], config.ssh_keys)
        self.assertEqual('heat-admin', config.users[0]['name'])

    def test_success(self, mock_pr):
        pr = mock_pr.return_value
        action = baremetal_deploy.DeployNodeAction(
            instance={'hostname': 'host1',
                      'image': 'overcloud-alt',
                      'nics': [{'port': 'abcd'}],
                      'root_size_gb': 100,
                      'swap_size_mb': 4096},
            node='1234',
            ssh_keys=['ssh key contents'],
            ssh_user_name='admin',
        )
        result = action.run(mock.Mock())

        self.assertEqual(
            pr.provision_node.return_value.to_dict.return_value,
            result)
        pr.provision_node.assert_called_once_with(
            '1234',
            image=mock.ANY,
            nics=[{'port': 'abcd'}],
            hostname='host1',
            root_size_gb=100,
            swap_size_mb=4096,
            config=mock.ANY,
        )
        config = pr.provision_node.call_args[1]['config']
        self.assertEqual(['ssh key contents'], config.ssh_keys)
        self.assertEqual('admin', config.users[0]['name'])
        source = pr.provision_node.call_args[1]['image']
        self.assertIsInstance(source, sources.GlanceImage)
        # TODO(dtantsur): check the image when it's a public field

    def test_success_http_partition_image(self, mock_pr):
        action = baremetal_deploy.DeployNodeAction(
            instance={'hostname': 'host1',
                      'image': 'https://example/image',
                      'image_kernel': 'https://example/kernel',
                      'image_ramdisk': 'https://example/ramdisk',
                      'image_checksum': 'https://example/checksum'},
            node='1234'
        )
        result = action.run(mock.Mock())

        pr = mock_pr.return_value
        self.assertEqual(
            pr.provision_node.return_value.to_dict.return_value,
            result)
        pr.provision_node.assert_called_once_with(
            '1234',
            image=mock.ANY,
            nics=[{'network': 'ctlplane'}],
            hostname='host1',
            root_size_gb=49,
            swap_size_mb=None,
            config=mock.ANY,
        )
        config = pr.provision_node.call_args[1]['config']
        self.assertEqual([], config.ssh_keys)
        self.assertEqual('heat-admin', config.users[0]['name'])
        source = pr.provision_node.call_args[1]['image']
        self.assertIsInstance(source, sources.HttpPartitionImage)
        self.assertEqual('https://example/image', source.url)
        self.assertEqual('https://example/kernel', source.kernel_url)
        self.assertEqual('https://example/ramdisk', source.ramdisk_url)
        self.assertEqual('https://example/checksum', source.checksum_url)

    def test_success_file_partition_image(self, mock_pr):
        action = baremetal_deploy.DeployNodeAction(
            instance={'hostname': 'host1',
                      'image': 'file:///var/lib/ironic/image',
                      'image_kernel': 'file:///var/lib/ironic/kernel',
                      'image_ramdisk': 'file:///var/lib/ironic/ramdisk',
                      'image_checksum': 'abcd'},
            node='1234'
        )
        result = action.run(mock.Mock())

        pr = mock_pr.return_value
        self.assertEqual(
            pr.provision_node.return_value.to_dict.return_value,
            result)
        pr.provision_node.assert_called_once_with(
            '1234',
            image=mock.ANY,
            nics=[{'network': 'ctlplane'}],
            hostname='host1',
            root_size_gb=49,
            swap_size_mb=None,
            config=mock.ANY,
        )
        config = pr.provision_node.call_args[1]['config']
        self.assertEqual([], config.ssh_keys)
        self.assertEqual('heat-admin', config.users[0]['name'])
        source = pr.provision_node.call_args[1]['image']
        self.assertIsInstance(source, sources.FilePartitionImage)
        self.assertEqual('file:///var/lib/ironic/image', source.location)
        self.assertEqual('file:///var/lib/ironic/kernel',
                         source.kernel_location)
        self.assertEqual('file:///var/lib/ironic/ramdisk',
                         source.ramdisk_location)
        self.assertEqual('abcd', source.checksum)

    @mock.patch.object(baremetal_deploy.LOG, 'exception', autospec=True)
    def test_failure(self, mock_log, mock_pr):
        pr = mock_pr.return_value
        instance = {'hostname': 'host1'}
        action = baremetal_deploy.DeployNodeAction(
            instance=instance,
            node='1234'
        )
        pr.provision_node.side_effect = RuntimeError('boom')
        result = action.run(mock.Mock())

        self.assertIn('RuntimeError: boom', result.error)
        pr.provision_node.assert_called_once_with(
            '1234',
            image=mock.ANY,
            nics=[{'network': 'ctlplane'}],
            hostname='host1',
            root_size_gb=49,
            swap_size_mb=None,
            config=mock.ANY,
        )
        pr.unprovision_node.assert_called_once_with('1234')
        mock_log.assert_called_once_with(
            'Provisioning of %s on node %s failed',
            instance, '1234')

    @mock.patch.object(baremetal_deploy.LOG, 'exception', autospec=True)
    def test_failure_to_clean_up(self, mock_log, mock_pr):
        pr = mock_pr.return_value
        instance = {'hostname': 'host1'}
        action = baremetal_deploy.DeployNodeAction(
            instance=instance,
            node='1234'
        )
        pr.provision_node.side_effect = RuntimeError('boom')
        pr.unprovision_node.side_effect = AssertionError
        result = action.run(mock.Mock())

        self.assertIn('RuntimeError: boom', result.error)
        pr.provision_node.assert_called_once_with(
            '1234',
            image=mock.ANY,
            nics=[{'network': 'ctlplane'}],
            hostname='host1',
            root_size_gb=49,
            swap_size_mb=None,
            config=mock.ANY,
        )
        pr.unprovision_node.assert_called_once_with('1234')
        mock_log.assert_has_calls([
            mock.call('Provisioning of %s on node %s failed',
                      instance, '1234'),
            mock.call('Unable to release node %s, moving on', '1234')
        ])


@mock.patch.object(baremetal_deploy, '_provisioner', autospec=True)
class TestCheckExistingInstances(base.TestCase):

    def test_success(self, mock_pr):
        pr = mock_pr.return_value
        instances = [
            {'hostname': 'host1'},
            {'hostname': 'host3'},
            {'hostname': 'host2', 'resource_class': 'compute',
             'capabilities': {'answer': '42'}}
        ]
        existing = mock.MagicMock(hostname='host2')
        pr.show_instance.side_effect = [
            sdk_exc.ResourceNotFound(""),
            metalsmith.exceptions.Error(""),
            existing,
        ]
        action = baremetal_deploy.CheckExistingInstancesAction(instances)
        result = action.run(mock.Mock())

        self.assertEqual({
            'instances': [existing.to_dict.return_value],
            'not_found': [{'hostname': 'host1', 'image': 'overcloud-full'},
                          {'hostname': 'host3', 'image': 'overcloud-full'}]
        }, result)
        pr.show_instance.assert_has_calls([
            mock.call(host) for host in ['host1', 'host3', 'host2']
        ])

    def test_missing_hostname(self, mock_pr):
        instances = [
            {'hostname': 'host1'},
            {'resource_class': 'compute', 'capabilities': {'answer': '42'}}
        ]
        action = baremetal_deploy.CheckExistingInstancesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn("'hostname' is a required property", result.error)
        self.assertFalse(mock_pr.return_value.show_instance.called)

    def test_hostname_mismatch(self, mock_pr):
        instances = [
            {'hostname': 'host1'},
        ]
        mock_pr.return_value.show_instance.return_value.hostname = 'host2'
        action = baremetal_deploy.CheckExistingInstancesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn("hostname host1 was not found", result.error)
        mock_pr.return_value.show_instance.assert_called_once_with('host1')

    def test_unexpected_error(self, mock_pr):
        instances = [
            {'hostname': 'host%d' % i} for i in range(3)
        ]
        mock_pr.return_value.show_instance.side_effect = RuntimeError('boom')
        action = baremetal_deploy.CheckExistingInstancesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn("hostname host0", result.error)
        self.assertIn("RuntimeError: boom", result.error)
        mock_pr.return_value.show_instance.assert_called_once_with('host0')


@mock.patch.object(baremetal_deploy, '_provisioner', autospec=True)
class TestWaitForDeployment(base.TestCase):

    def test_success(self, mock_pr):
        pr = mock_pr.return_value
        action = baremetal_deploy.WaitForDeploymentAction(
            {'hostname': 'compute.cloud', 'uuid': 'uuid1'})
        result = action.run(mock.Mock())

        pr.wait_for_provisioning.assert_called_once_with(['uuid1'],
                                                         timeout=3600)
        inst = pr.wait_for_provisioning.return_value[0]
        self.assertIs(result, inst.to_dict.return_value)

    def test_failure(self, mock_pr):
        pr = mock_pr.return_value
        pr.wait_for_provisioning.side_effect = RuntimeError('boom')
        action = baremetal_deploy.WaitForDeploymentAction(
            {'hostname': 'compute.cloud', 'uuid': 'uuid1'})
        result = action.run(mock.Mock())

        self.assertIn("RuntimeError: boom", result.error)
        pr.wait_for_provisioning.assert_called_once_with(['uuid1'],
                                                         timeout=3600)
        self.assertFalse(pr.unprovision_node.called)


@mock.patch.object(baremetal_deploy, '_provisioner', autospec=True)
class TestUndeployInstance(base.TestCase):

    def test_success(self, mock_pr):
        pr = mock_pr.return_value
        action = baremetal_deploy.UndeployInstanceAction('inst1')
        result = action.run(mock.Mock())
        self.assertIsNone(result)

        pr.show_instance.assert_called_once_with('inst1')
        pr.unprovision_node.assert_called_once_with(
            pr.show_instance.return_value.node, wait=1800)

    def test_not_found(self, mock_pr):
        pr = mock_pr.return_value
        pr.show_instance.side_effect = RuntimeError('not found')
        action = baremetal_deploy.UndeployInstanceAction('inst1')
        result = action.run(mock.Mock())
        self.assertIsNone(result)

        pr.show_instance.assert_called_once_with('inst1')
        self.assertFalse(pr.unprovision_node.called)
