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
import logging

import ironic_inspector_client
from mistral.workflow import utils as mistral_workflow_utils
from oslo_utils import units

from tripleo_common.actions import base
from tripleo_common import exception
from tripleo_common.utils import glance
from tripleo_common.utils import nodes

LOG = logging.getLogger(__name__)


class RegisterOrUpdateNodes(base.TripleOAction):
    """Register Nodes Action

    :param nodes_json: list of nodes & attributes in json format
    :param remove: Should nodes not in the list be removed?
    :param kernel_name: Glance ID of the kernel to use for the nodes.
    :param ramdisk_name: Glance ID of the ramdisk to use for the nodes.
    :param instance_boot_option: Whether to set instances for booting from
                                 local hard drive (local) or network (netboot).
    :return: list of node objects representing the new nodes.
    """

    def __init__(self, nodes_json, remove=False, kernel_name=None,
                 ramdisk_name=None, instance_boot_option='local'):
        super(RegisterOrUpdateNodes, self).__init__()
        self.nodes_json = nodes_json
        self.remove = remove
        self.instance_boot_option = instance_boot_option
        self.kernel_name = kernel_name
        self.ramdisk_name = ramdisk_name

    def run(self):
        for node in self.nodes_json:
            caps = node.get('capabilities', {})
            caps = nodes.capabilities_to_dict(caps)
            caps.setdefault('boot_option', self.instance_boot_option)
            node['capabilities'] = nodes.dict_to_capabilities(caps)

        baremetal_client = self._get_baremetal_client()
        image_client = self._get_image_client()

        try:
            return nodes.register_all_nodes(
                self.nodes_json,
                client=baremetal_client,
                remove=self.remove,
                glance_client=image_client,
                kernel_name=self.kernel_name,
                ramdisk_name=self.ramdisk_name,
                provide=False)
        except Exception as err:
            LOG.exception("Error registering nodes with ironic.")
            return mistral_workflow_utils.Result(
                "",
                err.message
            )


class ConfigureBootAction(base.TripleOAction):
    """Configure kernel and ramdisk.

    :param node_uuid: an Ironic node UUID
    :param kernel_name: Glance name of the kernel to use for the nodes.
    :param ramdisk_name: Glance name of the ramdisk to use for the nodes.
    :param instance_boot_option: Whether to set instances for booting from
                                 local hard drive (local) or network (netboot).
    """

    def __init__(self, node_uuid, kernel_name='bm-deploy-kernel',
                 ramdisk_name='bm-deploy-ramdisk', instance_boot_option=None):
        super(ConfigureBootAction, self).__init__()
        self.node_uuid = node_uuid
        self.kernel_name = kernel_name
        self.ramdisk_name = ramdisk_name
        self.instance_boot_option = instance_boot_option

    def run(self):
        baremetal_client = self._get_baremetal_client()
        image_client = self._get_image_client()

        try:
            image_ids = {'kernel': None, 'ramdisk': None}
            if self.kernel_name is not None and self.ramdisk_name is not None:
                image_ids = glance.create_or_find_kernel_and_ramdisk(
                    image_client, self.kernel_name, self.ramdisk_name)

            node = baremetal_client.node.get(self.node_uuid)

            capabilities = node.properties.get('capabilities', {})
            capabilities = nodes.capabilities_to_dict(capabilities)
            if self.instance_boot_option is not None:
                capabilities['boot_option'] = self.instance_boot_option
            else:
                # Add boot option capability if it didn't exist
                capabilities.setdefault(
                    'boot_option', self.instance_boot_option or 'local')
            capabilities = nodes.dict_to_capabilities(capabilities)

            baremetal_client.node.update(node.uuid, [
                {
                    'op': 'add',
                    'path': '/properties/capabilities',
                    'value': capabilities,
                },
                {
                    'op': 'add',
                    'path': '/driver_info/deploy_ramdisk',
                    'value': image_ids['ramdisk'],
                },
                {
                    'op': 'add',
                    'path': '/driver_info/deploy_kernel',
                    'value': image_ids['kernel'],
                },
            ])
            LOG.debug("Configuring boot option for Node %s", self.node_uuid)
        except Exception as err:
            LOG.exception("Error configuring node boot options with Ironic.")
            return mistral_workflow_utils.Result("", err)


class ConfigureRootDeviceAction(base.TripleOAction):
    """Configure the root device strategy.

    :param node_uuid: an Ironic node UUID
    :param root_device: Define the root device for nodes. Can be either a list
                        of device names (without /dev) to choose from or one
                        of two strategies: largest or smallest. For it to work
                        this command should be run after the introspection.
    :param minimum_size: Minimum size (in GiB) of the detected root device.
    :param overwrite: Whether to overwrite existing root device hints when
                      root-device is set.
    """

    def __init__(self, node_uuid, root_device=None, minimum_size=4,
                 overwrite=False):
        super(ConfigureRootDeviceAction, self).__init__()
        self.node_uuid = node_uuid
        self.root_device = root_device
        self.minimum_size = minimum_size
        self.overwrite = overwrite

    def run(self):
        if not self.root_device:
            return

        baremetal_client = self._get_baremetal_client()
        node = baremetal_client.node.get(self.node_uuid)
        self._apply_root_device_strategy(
            node, self.root_device, self.minimum_size, self.overwrite)

    def _apply_root_device_strategy(self, node, strategy, minimum_size,
                                    overwrite=False):
        if node.properties.get('root_device') and not overwrite:
            # This is a correct situation, we still want to allow people to
            # fine-tune the root device setting for a subset of nodes.
            # However, issue a warning, so that they know which nodes were not
            # updated during this run.
            LOG.warning('Root device hints are already set for node %s '
                        'and overwriting is not requested, skipping',
                        node.uuid)
            LOG.warning('You may unset them by running $ ironic '
                        'node-update %s remove properties/root_device',
                        node.uuid)
            return

        inspector_client = self._get_baremetal_introspection_client()
        try:
            data = inspector_client.get_data(node.uuid)
        except ironic_inspector_client.ClientError:
            raise exception.RootDeviceDetectionError(
                'No introspection data found for node %s, '
                'root device cannot be detected' % node.uuid)
        except AttributeError:
            raise RuntimeError('Ironic inspector client version 1.2.0 or '
                               'newer is required for detecting root device')

        try:
            disks = data['inventory']['disks']
        except KeyError:
            raise exception.RootDeviceDetectionError(
                'Malformed introspection data for node %s: '
                'disks list is missing' % node.uuid)

        minimum_size *= units.Gi
        disks = [d for d in disks if d.get('size', 0) >= minimum_size]

        if not disks:
            raise exception.RootDeviceDetectionError(
                'No suitable disks found for node %s' % node.uuid)

        if strategy == 'smallest':
            disks.sort(key=lambda d: d['size'])
            root_device = disks[0]
        elif strategy == 'largest':
            disks.sort(key=lambda d: d['size'], reverse=True)
            root_device = disks[0]
        else:
            disk_names = [x.strip() for x in strategy.split(',')]
            disks = {d['name']: d for d in disks}
            for candidate in disk_names:
                try:
                    root_device = disks['/dev/%s' % candidate]
                except KeyError:
                    continue
                else:
                    break
            else:
                raise exception.RootDeviceDetectionError(
                    'Cannot find a disk with any of names %(strategy)s '
                    'for node %(node)s' %
                    {'strategy': strategy, 'node': node.uuid})

        hint = None
        for hint_name in ('wwn', 'serial'):
            if root_device.get(hint_name):
                hint = {hint_name: root_device[hint_name]}
                break

        if hint is None:
            # I don't think it might actually happen, but just in case
            raise exception.RootDeviceDetectionError(
                'Neither WWN nor serial number are known for device %(dev)s '
                'on node %(node)s; root device hints cannot be used' %
                {'dev': root_device['name'], 'node': node.uuid})

        # During the introspection process we got local_gb assigned according
        # to the default strategy. Now we need to update it.
        new_size = root_device['size'] / units.Gi
        # This -1 is what we always do to account for partitioning
        new_size -= 1

        bm_client = self._get_baremetal_client()
        bm_client.node.update(
            node.uuid,
            [{'op': 'add', 'path': '/properties/root_device', 'value': hint},
             {'op': 'add', 'path': '/properties/local_gb', 'value': new_size}])

        LOG.info('Updated root device for node %(node)s, new device '
                 'is %(dev)s, new local_gb is %(local_gb)d',
                 {'node': node.uuid, 'dev': root_device, 'local_gb': new_size})


class UpdateNodeCapability(base.TripleOAction):
    """Update a node's capability

    Set the node's capability to the specified value.

    :param node_uuid: The UUID of the node
    :param capability: The name of the capability to update
    :param value: The value to update token
    :return: Result of updating the node
    """

    def __init__(self, node_uuid, capability, value):
        super(UpdateNodeCapability, self).__init__()
        self.node_uuid = node_uuid
        self.capability = capability
        self.value = value

    def run(self):
        baremetal_client = self._get_baremetal_client()

        try:
            return nodes.update_node_capability(
                self.node_uuid,
                self.capability,
                self.value,
                baremetal_client
            )
        except Exception as err:
            LOG.exception("Error updating node capability in ironic.")
            return mistral_workflow_utils.Result(
                "",
                "%s: %s" % (type(err).__name__, str(err))
            )
