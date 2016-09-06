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

import logging
import re
import time

import six

from tripleo_common import exception
from tripleo_common.utils import glance

LOG = logging.getLogger(__name__)


class DriverInfo(object):
    """Class encapsulating field conversion logic."""
    DEFAULTS = {}

    def __init__(self, prefix, mapping, deprecated_mapping=None):
        self._prefix = prefix
        self._mapping = mapping
        self._deprecated_mapping = deprecated_mapping or {}

    def convert_key(self, key):
        if key in self._mapping:
            return self._mapping[key]
        elif key in self._deprecated_mapping:
            real = self._deprecated_mapping[key]
            LOG.warning('Key %s is deprecated, please use %s',
                        key, real)
            return real
        elif key.startswith(self._prefix):
            return key
        elif key != 'pm_type' and key.startswith('pm_'):
            LOG.warning('Key %s is not supported and will not be passed',
                        key)
        else:
            LOG.debug('Skipping key %s not starting with prefix %s',
                      key, self._prefix)

    def convert(self, fields):
        """Convert fields from instackenv.json format to ironic names."""
        result = self.DEFAULTS.copy()
        for key, value in fields.items():
            new_key = self.convert_key(key)
            if new_key is not None:
                result[new_key] = value
        return result

    def unique_id_from_fields(self, fields):
        """Return a string uniquely identifying a node in instackenv."""

    def unique_id_from_node(self, node):
        """Return a string uniquely identifying a node in ironic db."""


class PrefixedDriverInfo(DriverInfo):
    def __init__(self, prefix, deprecated_mapping=None,
                 has_port=False, address_field='address'):
        mapping = {
            'pm_addr': '%s_%s' % (prefix, address_field),
            'pm_user': '%s_username' % prefix,
            'pm_password': '%s_password' % prefix,
        }
        if has_port:
            mapping['pm_port'] = '%s_port' % prefix
        self._has_port = has_port

        super(PrefixedDriverInfo, self).__init__(
            prefix, mapping,
            deprecated_mapping=deprecated_mapping
        )

    def unique_id_from_fields(self, fields):
        result = fields['pm_addr']
        if self._has_port and 'pm_port' in fields:
            result = '%s:%s' % (result, fields['pm_port'])
        return result

    def unique_id_from_node(self, node):
        new_key = self.convert_key('pm_addr')
        assert new_key is not None
        try:
            result = node.driver_info[new_key]
        except KeyError:
            # Node cannot be identified
            return

        if self._has_port:
            new_port = self.convert_key('pm_port')
            assert new_port
            try:
                return '%s:%s' % (result, node.driver_info[new_port])
            except KeyError:
                pass

        return result


class SshDriverInfo(DriverInfo):
    DEFAULTS = {'ssh_virt_type': 'virsh'}

    def __init__(self):
        super(SshDriverInfo, self).__init__(
            'ssh',
            {
                'pm_addr': 'ssh_address',
                'pm_user': 'ssh_username',
                # TODO(dtantsur): support ssh_key_filename as well
                'pm_password': 'ssh_key_contents',
            },
            deprecated_mapping={
                'pm_virt_type': 'ssh_virt_type',
            }
        )


class iBootDriverInfo(PrefixedDriverInfo):
    def __init__(self):
        super(iBootDriverInfo, self).__init__(
            'iboot', has_port=True,
            deprecated_mapping={
                'pm_relay_id': 'iboot_relay_id',
            }
        )

    def unique_id_from_fields(self, fields):
        result = super(iBootDriverInfo, self).unique_id_from_fields(fields)
        if 'iboot_relay_id' in fields:
            result = '%s#%s' % (result, fields['iboot_relay_id'])
        return result

    def unique_id_from_node(self, node):
        try:
            result = super(iBootDriverInfo, self).unique_id_from_node(node)
        except IndexError:
            return

        if node.driver_info.get('iboot_relay_id'):
            result = '%s#%s' % (result, node.driver_info['iboot_relay_id'])

        return result


DRIVER_INFO = {
    # production drivers
    '.*_ipmi(tool|native)': PrefixedDriverInfo('ipmi', has_port=True),
    '.*_drac': PrefixedDriverInfo('drac', address_field='host'),
    '.*_ilo': PrefixedDriverInfo('ilo'),
    '.*_ucs': PrefixedDriverInfo(
        'ucs',
        deprecated_mapping={
            'pm_service_profile': 'ucs_service_profile'
        }),
    '.*_irmc': PrefixedDriverInfo(
        'irmc', has_port=True,
        deprecated_mapping={
            'pm_auth_method': 'irmc_auth_method',
            'pm_client_timeout': 'irmc_client_timeout',
            'pm_sensor_method': 'irmc_sensor_method',
            'pm_deploy_iso': 'irmc_deploy_iso',
        }),
    # test drivers
    '.*_ssh': SshDriverInfo(),
    '.*_iboot': iBootDriverInfo(),
    '.*_wol': DriverInfo(
        'wol',
        mapping={
            'pm_addr': 'wol_host',
            'pm_port': 'wol_port',
        }),
    '.*_amt': PrefixedDriverInfo('amt'),
    'fake(|_pxe|_agent)': DriverInfo('fake', mapping={}),
}


def _find_driver_handler(driver):
    for driver_tpl, handler in DRIVER_INFO.items():
        if re.match(driver_tpl, driver) is not None:
            return handler

    # FIXME(dtantsur): handle all drivers without hardcoding them
    raise exception.InvalidNode('unknown pm_type (ironic driver to use): '
                                '%s' % driver)


def _find_node_handler(fields):
    try:
        driver = fields['pm_type']
    except KeyError:
        raise exception.InvalidNode('pm_type (ironic driver to use) is '
                                    'required', node=fields)
    return _find_driver_handler(driver)


def register_ironic_node(node, client=None, blocking=None):
    if blocking is not None:
        LOG.warning('blocking argument to register_ironic_node is deprecated '
                    'and does nothing')

    driver_info = {}
    handler = _find_node_handler(node)

    if "kernel_id" in node:
        driver_info["deploy_kernel"] = node["kernel_id"]
    if "ramdisk_id" in node:
        driver_info["deploy_ramdisk"] = node["ramdisk_id"]

    driver_info.update(handler.convert(node))

    mapping = {'cpus': 'cpu',
               'memory_mb': 'memory',
               'local_gb': 'disk',
               'cpu_arch': 'arch'}
    properties = {k: six.text_type(node.get(v))
                  for k, v in mapping.items()
                  if node.get(v) is not None}

    if 'capabilities' in node:
        caps = node['capabilities']
        if isinstance(caps, dict):
            caps = dict_to_capabilities(caps)
        properties.update({"capabilities": six.text_type(caps)})

    create_map = {"driver": node["pm_type"],
                  "properties": properties,
                  "driver_info": driver_info}

    for field in ('name', 'uuid'):
        if field in node:
            create_map.update({field: six.text_type(node[field])})

    node_id = handler.unique_id_from_fields(node)
    LOG.debug('Registering node %s with ironic.', node_id)
    ironic_node = client.node.create(**create_map)

    for mac in node.get("mac", []):
        client.port.create(address=mac, node_uuid=ironic_node.uuid)

    validation = client.node.validate(ironic_node.uuid)
    if not validation.power['result']:
        LOG.warning('Node %s did not pass power credentials validation: %s',
                    ironic_node.uuid, validation.power['reason'])

    return ironic_node


def _populate_node_mapping(client):
    LOG.debug('Populating list of registered nodes.')
    node_map = {'mac': {}, 'pm_addr': {}, 'uuids': set()}
    nodes = client.node.list(detail=True)
    for node in nodes:
        for port in client.node.list_ports(node.uuid):
            node_map['mac'][port.address] = node.uuid

        handler = _find_driver_handler(node.driver)
        unique_id = handler.unique_id_from_node(node)
        if unique_id:
            node_map['pm_addr'][unique_id] = node.uuid

        node_map['uuids'].add(node.uuid)

    return node_map


def _get_node_id(node, handler, node_map):
    candidates = set()
    for mac in node.get('mac', []):
        try:
            candidates.add(node_map['mac'][mac.lower()])
        except KeyError:
            pass

    unique_id = handler.unique_id_from_fields(node)
    if unique_id:
        try:
            candidates.add(node_map['pm_addr'][unique_id])
        except KeyError:
            pass

    uuid = node.get('uuid')
    if uuid and uuid in node_map['uuids']:
        candidates.add(uuid)

    if len(candidates) > 1:
        raise exception.InvalidNode('Several candidates found for the same '
                                    'node data: %s' % candidates,
                                    node=node)
    elif candidates:
        return list(candidates)[0]


def _update_or_register_ironic_node(node, node_map, client=None):
    handler = _find_node_handler(node)
    node_uuid = _get_node_id(node, handler, node_map)

    if node_uuid:
        LOG.info('Node %s already registered, updating details.',
                 node_uuid)

        patched = {}
        for field, path in [('cpu', '/properties/cpus'),
                            ('memory', '/properties/memory_mb'),
                            ('disk', '/properties/local_gb'),
                            ('arch', '/properties/cpu_arch'),
                            ('name', '/name'),
                            ('kernel_id', '/driver_info/deploy_kernel'),
                            ('ramdisk_id', '/driver_info/deploy_ramdisk'),
                            ('capabilities', '/properties/capabilities')]:
            if field in node:
                patched[path] = node.pop(field)

        driver_info = handler.convert(node)
        for key, value in driver_info.items():
            patched['/driver_info/%s' % key] = value

        node_patch = []
        for key, value in patched.items():
            if key == 'uuid':
                continue  # not needed during update
            node_patch.append({'path': key,
                               'value': six.text_type(value),
                               'op': 'add'})
        ironic_node = client.node.update(node_uuid, node_patch)
    else:
        ironic_node = register_ironic_node(node, client)

    return ironic_node


def _clean_up_extra_nodes(seen, client, remove=False):
    all_nodes = {n.uuid for n in client.node.list()}
    remove_func = client.node.delete
    extra_nodes = all_nodes - {n.uuid for n in seen}
    for node in extra_nodes:
        if remove:
            LOG.debug('Removing extra registered node %s.' % node)
            remove_func(node)
        else:
            LOG.debug('Extra registered node %s found.' % node)


def wait_for_provision_state(baremetal_client, node_uuid, provision_state,
                             loops=10, sleep=1):
    """Wait for a given Provisioning state in Ironic

    Updating the provisioning state is an async operation, we
    need to wait for it to be completed.

    :param baremetal_client: Instance of Ironic client
    :type  baremetal_client: ironicclient.v1.client.Client

    :param node_uuid: The Ironic node UUID
    :type  node_uuid: str

    :param provision_state: The provisioning state name to wait for
    :type  provision_state: str

    :param loops: How many times to loop
    :type loops: int

    :param sleep: How long to sleep between loops
    :type sleep: int

    :raises exceptions.StateTransitionFailed: if node.last_error is set
    """

    for _l in range(0, loops):

        # This will throw an exception if the UUID is not found, so no need to
        # check for node == None
        node = baremetal_client.node.get(node_uuid)

        if node.provision_state == provision_state:
            LOG.info('Node %s set to provision state %s',
                     node_uuid, provision_state)
            return

        # node.last_error should be None after any successful operation
        if node.last_error:
            raise exception.StateTransitionFailed(node, provision_state)

        time.sleep(sleep)

    raise exception.Timeout(
        "Node %(uuid)s did not reach provision state %(state)s. "
        "Now in state %(actual)s." % {
            'uuid': node_uuid,
            'state': provision_state,
            'actual': node.provision_state
        }
    )


def set_nodes_state(baremetal_client, nodes, transition, target_state,
                    skipped_states=()):
    """Make all nodes available in the baremetal service for a deployment

    For each node whose provision_state is not in skipped_states, apply the
    specified transition and wait until its provision_state is target_state.

    :param baremetal_client: Instance of Ironic client
    :type  baremetal_client: ironicclient.v1.client.Client

    :param nodes: List of Baremetal Nodes
    :type  nodes: [ironicclient.v1.node.Node]

    :param transition: The state to set for a node. The full list of states
                       can be found in ironic.common.states.
    :type  transition: string

    :param target_state: The expected result state for a node. For example when
                         transitioning to 'manage' the result is 'manageable'
    :type  target_state: string

    :param skipped_states: A set of states to skip, for example 'active' nodes
                           are already deployed and the state can't always be
                           changed.
    :type  skipped_states: iterable of strings

    :raises exception.Timeout: if a node takes too long to reach target state

    :return List of nodes whose provision states have been altered. These
            objects will be stale, and will not reflect the real node's current
            provision_state.
    """

    log = logging.getLogger(__name__ + ".set_nodes_state")
    altered_nodes = []

    for node in nodes:

        if node.provision_state in skipped_states:
            continue

        log.debug(
            "Setting provision state from '{0}' to '{1}' for Node {2}"
            .format(node.provision_state, transition, node.uuid))

        baremetal_client.node.set_provision_state(node.uuid, transition)
        try:
            wait_for_provision_state(baremetal_client, node.uuid, target_state)
        except exception.StateTransitionFailed as e:
            log.error("FAIL: {0}".format(e))
        except exception.Timeout as e:
            log.error("FAIL: {0}".format(e))
        altered_nodes.append(node)

    return altered_nodes


def register_all_nodes(nodes_list, client=None, remove=False, blocking=True,
                       keystone_client=None, glance_client=None,
                       kernel_name=None, ramdisk_name=None, provide=True):
    """Register all nodes in nodes_list in the baremetal service.

    :param nodes_list: The list of nodes to register.
    :param client: An Ironic client object.
    :param remove: Should nodes not in the list be removed?
    :param blocking: Ignored.
    :param keystone_client: Ignored.
    :param glance_client: A Glance client object, for fetching ramdisk images.
    :param kernel_name: Glance ID of the kernel to use for the nodes.
    :param ramdisk_name: Glance ID of the ramdisk to use for the nodes.
    :param provide: Should the node be transitioned to AVAILABLE state?
    :return: list of node objects representing the new nodes.
    """

    LOG.debug('Registering all nodes.')
    node_map = _populate_node_mapping(client)

    glance_ids = {'kernel': None, 'ramdisk': None}
    if kernel_name and ramdisk_name:
        glance_ids = glance.create_or_find_kernel_and_ramdisk(
            glance_client, kernel_name, ramdisk_name)

    seen = []
    for node in nodes_list:
        if glance_ids['kernel'] and 'kernel_id' not in node:
            node['kernel_id'] = glance_ids['kernel']
        if glance_ids['ramdisk'] and 'ramdisk_id' not in node:
            node['ramdisk_id'] = glance_ids['ramdisk']

        node = _update_or_register_ironic_node(node, node_map, client=client)
        seen.append(node)

    _clean_up_extra_nodes(seen, client, remove=remove)

    if provide:
        manageable_nodes = set_nodes_state(
            client, seen, "manage", "manageable",
            skipped_states={'manageable', 'available'}
        )
        set_nodes_state(
            client, manageable_nodes, "provide", "available",
            skipped_states={'available'}
        )

    return seen


def dict_to_capabilities(caps_dict):
    """Convert a dictionary into a string with the capabilities syntax."""
    return ','.join(["%s:%s" % (key, value)
                     for key, value in caps_dict.items()
                     if value is not None])


def capabilities_to_dict(caps):
    """Convert the Node's capabilities into a dictionary."""
    if not caps:
        return {}
    if isinstance(caps, dict):
        return caps
    return dict([key.split(':', 1) for key in caps.split(',')])


def _get_capability_patch(node, capability, value):
    """Return a JSON patch updating a node capability"""
    capabilities = node.properties.get('capabilities')
    capabilities_dict = capabilities_to_dict(capabilities)

    if value is None:
        del capabilities_dict[capability]
    else:
        capabilities_dict[capability] = value

    capabilities = dict_to_capabilities(capabilities_dict)

    return [{
        "op": "replace",
        "path": "/properties/capabilities",
        "value": capabilities
    }]


def update_node_capability(node_uuid, capability, value, client):
    """Update a node's capability

    :param node_uuid: The UUID of the node
    :param capability: The name of the capability to update
    :param value: The value to update token
    :param client: An Ironic client object
    :return: Result of updating the node
    """
    node = client.node.get(node_uuid)
    patch = _get_capability_patch(node, capability, value)
    return client.node.update(node_uuid, patch)
