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
            {'hostname': 'host1', 'profile': 'compute',
             'image': {'href': 'overcloud-full'}},
            {'hostname': 'host2', 'resource_class': 'compute',
             'capabilities': {'answer': '42'},
             'image': {'href': 'overcloud-full'}},
            {'name': 'control-0', 'traits': ['CUSTOM_GPU'],
             'image': {'href': 'overcloud-full'}},
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
            {'hostname': 'host1',
             'image': {'href': 'overcloud-full'}},
            {'resource_class': 'compute', 'capabilities': {'answer': '42'},
             'image': {'href': 'overcloud-full'}}
        ]
        action = baremetal_deploy.ReserveNodesAction(instances)
        result = action.run(mock.Mock())

        self.assertEqual(
            [{'node': mock_pr.return_value.reserve_node.return_value.id,
              'instance': req} for req in instances],
            result['reservations'])
        mock_pr.return_value.reserve_node.assert_has_calls([
            mock.call(resource_class='baremetal', traits=None,
                      capabilities=None, candidates=None),
            mock.call(resource_class='compute', traits=None,
                      capabilities={'answer': '42'}, candidates=None),
        ])

        self.assertFalse(mock_pr.return_value.unprovision_node.called)

    @mock.patch.object(baremetal_deploy.LOG, 'exception', autospec=True)
    def test_failure(self, mock_log, mock_pr):
        instances = [
            {'hostname': 'host1',
             'image': {'href': 'overcloud-full'}},
            {'hostname': 'host2', 'resource_class': 'compute',
             'capabilities': {'answer': '42'},
             'image': {'href': 'overcloud-full'}},
            {'hostname': 'host3',
             'image': {'href': 'overcloud-full'}},
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
            {'hostname': 'host1',
             'image': {'href': 'overcloud-full'}},
            {'hostname': 'host2', 'resource_class': 'compute',
             'capabilities': {'answer': '42'},
             'image': {'href': 'overcloud-full'}},
            {'hostname': 'host3',
             'image': {'href': 'overcloud-full'}},
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
            {'hostname': 'host1',
             'image': {'href': 'overcloud-full'}},
            {'hostname': 'host1',
             'image': {'href': 'overcloud-full'}},
        ]
        action = baremetal_deploy.ReserveNodesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn('Hostname host1 is used more than once', result.error)
        self.assertFalse(mock_pr.return_value.reserve_node.called)

    def test_duplicate_name(self, mock_pr):
        instances = [
            {'hostname': 'host1', 'name': 'node-1',
             'image': {'href': 'overcloud-full'}},
            # name is used as the default for hostname
            {'name': 'node-1',
             'image': {'href': 'overcloud-full'}},
        ]
        action = baremetal_deploy.ReserveNodesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn('Node node-1 is requested more than once', result.error)
        self.assertFalse(mock_pr.return_value.reserve_node.called)

    def test_hostname_format(self, mock_pr):
        self.assertEqual(
            '%stackname%-controller-%index%',
            baremetal_deploy._hostname_format(None, 'Controller')
        )
        self.assertEqual(
            '%stackname%-novacompute-%index%',
            baremetal_deploy._hostname_format(None, 'Compute')
        )
        self.assertEqual(
            'server-%index%',
            baremetal_deploy._hostname_format('server-%index%', 'Compute')
        )

    def test_build_hostname(self, mock_pr):
        self.assertEqual(
            'overcloud-controller-2',
            baremetal_deploy._build_hostname(
                '%stackname%-controller-%index%', 2, 'overcloud'
            )
        )
        self.assertEqual(
            'server-2',
            baremetal_deploy._build_hostname(
                'server-%index%', 2, 'overcloud'
            )
        )


@mock.patch.object(baremetal_deploy, '_provisioner', autospec=True)
class TestDeployNode(base.TestCase):

    def test_success_defaults(self, mock_pr):
        action = baremetal_deploy.DeployNodeAction(
            instance={'hostname': 'host1',
                      'image': {'href': 'overcloud-full'}},
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
            instance={
                'name': 'host1',
                'hostname': 'host1',
                'image': {'href': 'overcloud-full'}
            },
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
                      'image': {'href': 'overcloud-full'},
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
                      'image': {'href': 'overcloud-alt'},
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
            instance={
                'hostname': 'host1',
                'image': {
                    'href': 'https://example/image',
                    'kernel': 'https://example/kernel',
                    'ramdisk': 'https://example/ramdisk',
                    'checksum': 'https://example/checksum'
                }
            },
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
            instance={
                'hostname': 'host1',
                'image': {
                    'href': 'file:///var/lib/ironic/image',
                    'kernel': 'file:///var/lib/ironic/kernel',
                    'ramdisk': 'file:///var/lib/ironic/ramdisk',
                    'checksum': 'abcd'
                }
            },
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
        instance = {'hostname': 'host1',
                    'image': {'href': 'overcloud-full'}}
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
        instance = {'hostname': 'host1',
                    'image': {'href': 'overcloud-full'}}
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
            {'hostname': 'host1',
             'image': {'href': 'overcloud-full'}},
            {'hostname': 'host3',
             'image': {'href': 'overcloud-full'}},
            {'hostname': 'host2', 'resource_class': 'compute',
             'capabilities': {'answer': '42'},
             'image': {'href': 'overcloud-full'}}
        ]
        existing = mock.MagicMock(hostname='host2', allocation=None)
        existing.to_dict.return_value = {
            'hostname': 'host2',
            'allocation': None
        }
        pr.show_instance.side_effect = [
            sdk_exc.ResourceNotFound(""),
            metalsmith.exceptions.Error(""),
            existing,
        ]
        action = baremetal_deploy.CheckExistingInstancesAction(instances)
        result = action.run(mock.Mock())

        self.assertEqual({
            'instances': [{
                'hostname': 'host2',
                'allocation': None,
                'port_map': {}
            }],
            'not_found': [{
                'hostname': 'host1',
                'image': {'href': 'overcloud-full'},
            }, {
                'hostname': 'host3',
                'image': {'href': 'overcloud-full'},
            }]
        }, result)
        pr.show_instance.assert_has_calls([
            mock.call(host) for host in ['host1', 'host3', 'host2']
        ])

    @mock.patch('tripleo_common.actions.baremetal_deploy.'
                'CheckExistingInstancesAction.get_baremetal_client')
    def test_existing_no_allocation(self, mock_gbc, mock_pr):
        pr = mock_pr.return_value
        instances = [
            {'name': 'server2', 'resource_class': 'compute',
             'hostname': 'host2',
             'capabilities': {'answer': '42'},
             'image': {'href': 'overcloud-full'}}
        ]
        existing = mock.MagicMock(
            hostname='host2', allocation=None,
            state=metalsmith.InstanceState.ACTIVE)
        existing.to_dict.return_value = {
            'hostname': 'host2',
        }
        pr.show_instance.return_value = existing
        mock_create = mock_gbc.return_value.allocation.create

        action = baremetal_deploy.CheckExistingInstancesAction(instances)
        ctx = mock.Mock()
        result = action.run(ctx)
        mock_gbc.assert_called_once_with(ctx)
        mock_create.assert_called_once_with(
            name='host2', node='server2', resource_class='compute')

        self.assertEqual({
            'instances': [{
                'hostname': 'host2',
                'port_map': {}
            }],
            'not_found': []
        }, result)
        pr.show_instance.assert_called_once_with('server2')

    def test_hostname_mismatch(self, mock_pr):
        instances = [
            {'hostname': 'host1',
             'image': {'href': 'overcloud-full'}},
        ]
        mock_pr.return_value.show_instance.return_value.hostname = 'host2'
        action = baremetal_deploy.CheckExistingInstancesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn("hostname host1 was not found", result.error)
        mock_pr.return_value.show_instance.assert_called_once_with('host1')

    def test_unexpected_error(self, mock_pr):
        instances = [
            {'image': {'href': 'overcloud-full'},
             'hostname': 'host%d' % i} for i in range(3)
        ]
        mock_pr.return_value.show_instance.side_effect = RuntimeError('boom')
        action = baremetal_deploy.CheckExistingInstancesAction(instances)
        result = action.run(mock.Mock())

        self.assertIn("for host0", result.error)
        self.assertIn("RuntimeError: boom", result.error)
        mock_pr.return_value.show_instance.assert_called_once_with('host0')


@mock.patch.object(baremetal_deploy, '_provisioner', autospec=True)
class TestWaitForDeployment(base.TestCase):

    def test_success(self, mock_pr):
        pr = mock_pr.return_value
        inst = pr.wait_for_provisioning.return_value[0]
        inst.to_dict.return_value = {'hostname': 'compute.cloud'}

        action = baremetal_deploy.WaitForDeploymentAction(
            {'hostname': 'compute.cloud', 'uuid': 'uuid1',
             'image': {'href': 'overcloud-full'}})
        result = action.run(mock.Mock())

        pr.wait_for_provisioning.assert_called_once_with(['uuid1'],
                                                         timeout=3600)
        self.assertIs(result, inst.to_dict.return_value)
        self.assertEqual({}, result['port_map'])

    def test_with_nics(self, mock_pr):
        pr = mock_pr.return_value
        net_mock = mock.Mock()
        net_mock.name = 'ctlplane'
        net_mock.to_dict.return_value = {'tags': ['foo']}
        inst = pr.wait_for_provisioning.return_value[0]
        inst.nics.return_value = [
            mock.Mock(fixed_ips=[{'ip_address': '1.2.3.5',
                                  'subnet_id': 'abcd'}],
                      network=net_mock)
        ]
        pr.connection.network.get_subnet.return_value.to_dict.return_value = {
            'cidr': '1.2.3.0/24'
        }
        inst.to_dict.return_value = {'hostname': 'compute.cloud'}

        action = baremetal_deploy.WaitForDeploymentAction(
            {'hostname': 'compute.cloud', 'uuid': 'uuid1'})
        result = action.run(mock.Mock())

        pr.wait_for_provisioning.assert_called_once_with(['uuid1'],
                                                         timeout=3600)
        self.assertIs(result, inst.to_dict.return_value)
        self.assertEqual(
            {
                'ctlplane': {
                    'network': {'tags': ['foo']},
                    'fixed_ips': [{'ip_address': '1.2.3.5'}],
                    'subnets': [{'cidr': '1.2.3.0/24'}],
                }
            },
            result['port_map'])

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
        # pylint: disable=assignment-from-none
        result = action.run(mock.Mock())
        self.assertIsNone(result)

        pr.show_instance.assert_called_once_with('inst1')
        pr.unprovision_node.assert_called_once_with(
            pr.show_instance.return_value.node, wait=1800)

    def test_not_found(self, mock_pr):
        pr = mock_pr.return_value
        pr.show_instance.side_effect = RuntimeError('not found')
        action = baremetal_deploy.UndeployInstanceAction('inst1')
        # pylint: disable=assignment-from-none
        result = action.run(mock.Mock())
        self.assertIsNone(result)

        pr.show_instance.assert_called_once_with('inst1')
        self.assertFalse(pr.unprovision_node.called)


class TestExpandRoles(base.TestCase):

    def test_simple(self):
        roles = [
            {'name': 'Compute'},
            {'name': 'Controller'},
        ]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual(
            [
                {'hostname': 'overcloud-novacompute-0',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'overcloud-controller-0',
                 'image': {'href': 'overcloud-full'}},
            ],
            result['instances'])
        self.assertEqual(
            {
                'ComputeHostnameFormat':
                '%stackname%-novacompute-%index%',
                'ComputeCount': 1,
                'ControllerHostnameFormat':
                '%stackname%-controller-%index%',
                'ControllerCount': 1,
                'HostnameMap': {
                    'overcloud-novacompute-0': 'overcloud-novacompute-0',
                    'overcloud-controller-0': 'overcloud-controller-0'
                }
            },
            result['environment']['parameter_defaults'])

    def test_image_in_defaults(self):
        roles = [{
            'name': 'Controller',
            'defaults': {
                'image': {
                    'href': 'file:///tmp/foo.qcow2',
                    'checksum': '12345678'
                }
            },
            'count': 3,
            'instances': [{
                'hostname': 'overcloud-controller-0',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'overcloud-controller-1',
            }]
        }]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual(
            [
                {'hostname': 'overcloud-controller-0',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'overcloud-controller-1',
                 'image': {'href': 'file:///tmp/foo.qcow2',
                           'checksum': '12345678'}},
                {'hostname': 'overcloud-controller-2',
                 'image': {'href': 'file:///tmp/foo.qcow2',
                           'checksum': '12345678'}},
            ],
            result['instances'])

    def test_with_parameters(self):
        roles = [{
            'name': 'Compute',
            'count': 2,
            'defaults': {
                'profile': 'compute'
            },
            'hostname_format': 'compute-%index%.example.com'
        }, {
            'name': 'Controller',
            'count': 3,
            'defaults': {
                'profile': 'control'
            },
            'hostname_format': 'controller-%index%.example.com'
        }]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual(
            [
                {'hostname': 'compute-0.example.com', 'profile': 'compute',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'compute-1.example.com', 'profile': 'compute',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'controller-0.example.com', 'profile': 'control',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'controller-1.example.com', 'profile': 'control',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'controller-2.example.com', 'profile': 'control',
                 'image': {'href': 'overcloud-full'}},
            ],
            result['instances'])
        self.assertEqual(
            {
                'ComputeHostnameFormat':
                'compute-%index%.example.com',
                'ComputeCount': 2,
                'ControllerHostnameFormat':
                'controller-%index%.example.com',
                'ControllerCount': 3,
                'HostnameMap': {
                    'compute-0.example.com': 'compute-0.example.com',
                    'compute-1.example.com': 'compute-1.example.com',
                    'controller-0.example.com': 'controller-0.example.com',
                    'controller-1.example.com': 'controller-1.example.com',
                    'controller-2.example.com': 'controller-2.example.com',
                }
            },
            result['environment']['parameter_defaults'])

    def test_explicit_instances(self):
        roles = [{
            'name': 'Compute',
            'count': 2,
            'defaults': {
                'profile': 'compute'
            },
            'hostname_format': 'compute-%index%.example.com'
        }, {
            'name': 'Controller',
            'count': 2,
            'defaults': {
                'profile': 'control'
            },
            'instances': [{
                'hostname': 'controller-X.example.com',
                'profile': 'control-X'
            }, {
                'name': 'node-0',
                'traits': ['CUSTOM_FOO'],
                'nics': [{'subnet': 'leaf-2'}]},
            ]},
        ]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual(
            [
                {'hostname': 'compute-0.example.com', 'profile': 'compute',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'compute-1.example.com', 'profile': 'compute',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'controller-X.example.com',
                 'image': {'href': 'overcloud-full'},
                 'profile': 'control-X'},
                # Name provides the default for hostname later on.
                {'name': 'node-0', 'profile': 'control',
                 'hostname': 'node-0',
                 'image': {'href': 'overcloud-full'},
                 'traits': ['CUSTOM_FOO'], 'nics': [{'subnet': 'leaf-2'}]},
            ],
            result['instances'])
        self.assertEqual(
            {
                'ComputeHostnameFormat':
                'compute-%index%.example.com',
                'ComputeCount': 2,
                'ControllerHostnameFormat':
                '%stackname%-controller-%index%',
                'ControllerCount': 2,
                'HostnameMap': {
                    'compute-0.example.com': 'compute-0.example.com',
                    'compute-1.example.com': 'compute-1.example.com',
                    'overcloud-controller-0': 'controller-X.example.com',
                    'overcloud-controller-1': 'node-0',
                }
            },
            result['environment']['parameter_defaults'])

    def test_count_with_instances(self):
        roles = [{
            'name': 'Compute',
            'count': 2,
            'defaults': {
                'profile': 'compute',
            },
            'hostname_format': 'compute-%index%.example.com'
        }, {
            'name': 'Controller',
            'defaults': {
                'profile': 'control',
            },
            'count': 3,
            'instances': [{
                'hostname': 'controller-X.example.com',
                'profile': 'control-X'
            }, {
                'name': 'node-0',
                'traits': ['CUSTOM_FOO'],
                'nics': [{'subnet': 'leaf-2'}]},
            ]},
        ]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual([
            {
                'hostname': 'compute-0.example.com',
                'profile': 'compute',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'compute-1.example.com',
                'profile': 'compute',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'controller-X.example.com',
                'profile': 'control-X',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'node-0',
                'name': 'node-0',
                'nics': [{'subnet': 'leaf-2'}],
                'profile': 'control',
                'traits': ['CUSTOM_FOO'],
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'overcloud-controller-2',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }],
            result['instances'])
        self.assertEqual({
            'ComputeCount': 2,
            'ComputeHostnameFormat':
                'compute-%index%.example.com',
            'ControllerCount': 3,
            'ControllerHostnameFormat':
                '%stackname%-controller-%index%',
            'HostnameMap': {
                'compute-0.example.com': 'compute-0.example.com',
                'compute-1.example.com': 'compute-1.example.com',
                'overcloud-controller-0': 'controller-X.example.com',
                'overcloud-controller-1': 'node-0',
                'overcloud-controller-2': 'overcloud-controller-2'}
            },
            result['environment']['parameter_defaults'])

    def test_unprovisioned(self):
        roles = [{
            'name': 'Controller',
            'defaults': {
                'profile': 'control',
            },
            'count': 2,
            'instances': [{
                'hostname': 'overcloud-controller-1',
                'provisioned': False
            }, {
                'hostname': 'overcloud-controller-2',
                'provisioned': False
            }]
        }]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual([
            {
                'hostname': 'overcloud-controller-0',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'overcloud-controller-3',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }],
            result['instances'])
        self.assertEqual({
            'ControllerCount': 2,
            'ControllerRemovalPolicies': [
                {'resource_list': [1, 2]}
            ],
            'ControllerHostnameFormat':
                '%stackname%-controller-%index%',
            'HostnameMap': {
                'overcloud-controller-0': 'overcloud-controller-0',
                'overcloud-controller-1': 'overcloud-controller-1',
                'overcloud-controller-2': 'overcloud-controller-2',
                'overcloud-controller-3': 'overcloud-controller-3'}
            },
            result['environment']['parameter_defaults'])

        # action for an unprovision workflow
        action = baremetal_deploy.ExpandRolesAction(roles, provisioned=False)
        result = action.run(mock.Mock())
        self.assertEqual([
            {
                'hostname': 'overcloud-controller-1',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'overcloud-controller-2',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }],
            result['instances'])
        self.assertEqual({}, result['environment'])

    def test_reprovisioned(self):
        roles = [{
            'name': 'Controller',
            'defaults': {
                'profile': 'control',
            },
            'count': 4,
            'instances': [{
                'hostname': 'overcloud-controller-1',
                'provisioned': False
            }, {
                'hostname': 'overcloud-controller-2',
                'provisioned': False
            }]
        }]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual([
            {
                'hostname': 'overcloud-controller-0',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'overcloud-controller-3',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'overcloud-controller-4',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'overcloud-controller-5',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }],
            result['instances'])
        self.assertEqual({
            'ControllerCount': 4,
            'ControllerRemovalPolicies': [
                {'resource_list': [1, 2]}
            ],
            'ControllerHostnameFormat':
                '%stackname%-controller-%index%',
            'HostnameMap': {
                'overcloud-controller-0': 'overcloud-controller-0',
                'overcloud-controller-1': 'overcloud-controller-1',
                'overcloud-controller-2': 'overcloud-controller-2',
                'overcloud-controller-3': 'overcloud-controller-3',
                'overcloud-controller-4': 'overcloud-controller-4',
                'overcloud-controller-5': 'overcloud-controller-5'}
            },
            result['environment']['parameter_defaults'])

        # action for an unprovision workflow
        action = baremetal_deploy.ExpandRolesAction(roles, provisioned=False)
        result = action.run(mock.Mock())
        self.assertEqual([
            {
                'hostname': 'overcloud-controller-1',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'overcloud-controller-2',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }],
            result['instances'])
        self.assertEqual({}, result['environment'])

    def test_unprovisioned_instances(self):
        roles = [{
            'name': 'Controller',
            'defaults': {
                'profile': 'control',
            },
            'count': 2,
            'instances': [{
                'name': 'node-0',
                'hostname': 'controller-0'
            }, {
                'name': 'node-1',
                'hostname': 'controller-1',
                'provisioned': False
            }, {
                'name': 'node-2',
                'hostname': 'controller-2',
                'provisioned': False
            }, {
                'name': 'node-3',
                'hostname': 'controller-3',
                'provisioned': True
            }]
        }]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual([
            {
                'hostname': 'controller-0',
                'name': 'node-0',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'controller-3',
                'name': 'node-3',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }],
            result['instances'])
        self.assertEqual({
            'ControllerCount': 2,
            'ControllerRemovalPolicies': [
                {'resource_list': [1, 2]}
            ],
            'ControllerHostnameFormat':
                '%stackname%-controller-%index%',
            'HostnameMap': {
                'overcloud-controller-0': 'controller-0',
                'overcloud-controller-1': 'controller-1',
                'overcloud-controller-2': 'controller-2',
                'overcloud-controller-3': 'controller-3'}
            },
            result['environment']['parameter_defaults'])

        # action for an unprovision workflow
        action = baremetal_deploy.ExpandRolesAction(roles, provisioned=False)
        result = action.run(mock.Mock())
        self.assertEqual([
            {
                'hostname': 'controller-1',
                'name': 'node-1',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'controller-2',
                'name': 'node-2',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }],
            result['instances'])
        self.assertEqual({}, result['environment'])

    def test_unprovisioned_no_hostname(self):
        roles = [{
            'name': 'Controller',
            'defaults': {
                'profile': 'control',
            },
            'count': 2,
            'instances': [{
                'name': 'node-0',
            }, {
                'name': 'node-1',
                'provisioned': False
            }, {
                'name': 'node-2',
                'provisioned': False
            }, {
                'name': 'node-3',
                'provisioned': True
            }]
        }]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual([
            {
                'hostname': 'node-0',
                'name': 'node-0',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'node-3',
                'name': 'node-3',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }],
            result['instances'])
        self.assertEqual({
            'ControllerCount': 2,
            'ControllerRemovalPolicies': [
                {'resource_list': [1, 2]}
            ],
            'ControllerHostnameFormat':
                '%stackname%-controller-%index%',
            'HostnameMap': {
                'overcloud-controller-0': 'node-0',
                'overcloud-controller-1': 'node-1',
                'overcloud-controller-2': 'node-2',
                'overcloud-controller-3': 'node-3'}
            },
            result['environment']['parameter_defaults'])

        # action for an unprovision workflow
        action = baremetal_deploy.ExpandRolesAction(roles, provisioned=False)
        result = action.run(mock.Mock())
        self.assertEqual([
            {
                'hostname': 'node-1',
                'name': 'node-1',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }, {
                'hostname': 'node-2',
                'name': 'node-2',
                'profile': 'control',
                'image': {'href': 'overcloud-full'}
            }],
            result['instances'])
        self.assertEqual({}, result['environment'])

    def test_name_in_defaults(self):
        roles = [{
            'name': 'Compute',
            'count': 2,
            'defaults': {
                'profile': 'compute',
                'name': 'compute-0'
            }
        }]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertIn('Compute: cannot specify name in defaults',
                      result.error)

    def test_hostname_in_defaults(self):
        roles = [{
            'name': 'Compute',
            'count': 2,
            'defaults': {
                'profile': 'compute',
                'hostname': 'compute-0'
            }
        }]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertIn('Compute: cannot specify hostname in defaults',
                      result.error)

    def test_instances_without_hostname(self):
        roles = [{
            'name': 'Compute',
            'count': 2,
            'defaults': {
                'profile': 'compute'
            },
            'hostname_format': 'compute-%index%.example.com'
        }, {
            'name': 'Controller',
            'count': 2,
            'defaults': {
                'profile': 'control'
            },
            'instances': [{
                'profile': 'control-X'
                # missing hostname here
            }, {
                'name': 'node-0',
                'traits': ['CUSTOM_FOO'],
                'nics': [{'subnet': 'leaf-2'}]},
            ]},
        ]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertEqual(
            [
                {'hostname': 'compute-0.example.com', 'profile': 'compute',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'compute-1.example.com', 'profile': 'compute',
                 'image': {'href': 'overcloud-full'}},
                {'hostname': 'overcloud-controller-0', 'profile': 'control-X',
                 'image': {'href': 'overcloud-full'}},
                # Name provides the default for hostname
                {'name': 'node-0', 'profile': 'control',
                 'hostname': 'node-0',
                 'image': {'href': 'overcloud-full'},
                 'traits': ['CUSTOM_FOO'], 'nics': [{'subnet': 'leaf-2'}]},
            ],
            result['instances'])

    def test_more_instances_than_count(self):
        roles = [{
            'name': 'Compute',
            'count': 3,
            'defaults': {
                'profile': 'compute',
                'name': 'compute-0'
            },
            'instances': [{
                'name': 'node-0'
            }, {
                'name': 'node-1'
            }, {
                'name': 'node-2'
            }, {
                'name': 'node-3'
            }]
        }]
        action = baremetal_deploy.ExpandRolesAction(roles)
        result = action.run(mock.Mock())
        self.assertIn('Compute: number of instance entries 4 '
                      'cannot be greater than count 3',
                      result.error)


class TestPopulateEnvironment(base.TestCase):

    def test_success(self):
        port_map = {
            'compute-0': {
                'ctlplane': {
                    'network': {
                        'tags': ['foo'],
                        'mtu': 1350,
                        'id': 'aaaa'  # will be filtered out
                    },
                    'fixed_ips': [{'ip_address': '1.2.3.5'}],
                    'subnets': [{
                        'cidr': '1.2.3.0/24',
                        'gateway_ip': '192.168.24.1',
                        'host_routes': [{
                            'destination': '169.254.169.254/32',
                            'nexthop': '192.168.24.3'
                        }],
                        'dns_nameservers': ['8.8.8.8'],
                        'id': 'bbbb'  # will be filtered out
                    }],
                },
                'foobar': {
                    'network': {},
                    'fixed_ips': [{'ip_address': '1.2.4.5'}],
                    'subnets': [{'cidr': '1.2.4.0/24'}],
                },
            },
            'controller-0': {
                'ctlplane': {
                    'network': {'tags': ['foo']},
                    'fixed_ips': [{'ip_address': '1.2.3.4'}],
                    'subnets': [{'cidr': '1.2.3.0/24'}],
                },
                'foobar': {
                    'network': {},
                    'fixed_ips': [{'ip_address': '1.2.4.4'}],
                    'subnets': [{'cidr': '1.2.4.0/24'}],
                },
            },
        }
        action = baremetal_deploy.PopulateEnvironmentAction({}, port_map)
        result = action.run(mock.Mock())
        self.assertEqual(
            {
                'resource_registry': {
                    'OS::TripleO::DeployedServer::ControlPlanePort':
                    '/usr/share/openstack-tripleo-heat-templates/'
                    'deployed-server/deployed-neutron-port.yaml'
                },
                'parameter_defaults': {
                    'DeployedServerPortMap': {
                        'compute-0-ctlplane': {
                            'fixed_ips': [{'ip_address': '1.2.3.5'}],
                            'subnets': [{
                                'cidr': '1.2.3.0/24',
                                'gateway_ip': '192.168.24.1',
                                'host_routes': [{
                                    'destination': '169.254.169.254/32',
                                    'nexthop': '192.168.24.3'
                                }],
                                'dns_nameservers': ['8.8.8.8'],
                            }],
                            'network': {
                                'tags': ['foo'],
                                'mtu': 1350,
                            },
                        },
                        'controller-0-ctlplane': {
                            'fixed_ips': [{'ip_address': '1.2.3.4'}],
                            'subnets': [{'cidr': '1.2.3.0/24'}],
                            'network': {'tags': ['foo']},
                        },
                    }
                }
            },
            result)
