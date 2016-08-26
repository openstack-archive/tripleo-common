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

from mistral.workflow import utils as mistral_workflow_utils
from tripleo_common.actions import base
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
                'service_host',  # unused
                self.nodes_json,
                client=baremetal_client,
                remove=self.remove,
                glance_client=image_client,
                kernel_name=self.kernel_name,
                ramdisk_name=self.ramdisk_name)
        except Exception as err:
            LOG.exception("Error registering nodes with ironic.")
            return mistral_workflow_utils.Result(
                "",
                err.message
            )
