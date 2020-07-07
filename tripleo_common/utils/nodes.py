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

from oslo_utils import netutils
import six

from ironicclient import exceptions as ironicexceptions
from oslo_concurrency import processutils
from tripleo_common import exception
from tripleo_common.utils import glance

LOG = logging.getLogger(__name__)

_KNOWN_INTERFACE_FIELDS = [
    '%s_interface' % field for field in ('boot', 'console', 'deploy',
                                         'inspect', 'management', 'network',
                                         'power', 'raid', 'rescue', 'storage',
                                         'vendor')
]

CTLPLANE_NETWORK = 'ctlplane'


def convert_nodes_json_mac_to_ports(nodes_json):
    for node in nodes_json:
        if node.get('mac'):
            LOG.warning('Key mac is deprecated, please use ports.')
            for address in node['mac']:
                try:
                    node['ports'].append({'address': address})
                except KeyError:
                    node['ports'] = [{'address': address}]
            del node['mac']

    return nodes_json


class DriverInfo(object):
    """Class encapsulating field conversion logic."""
    DEFAULTS = {}

    def __init__(self, prefix, mapping, deprecated_mapping=None,
                 mandatory_fields=(), default_port=None, hardware_type=None):
        self._prefix = prefix
        self._mapping = mapping
        self._deprecated_mapping = deprecated_mapping or {}
        self._mandatory_fields = mandatory_fields
        self._default_port = default_port
        self._hardware_type = hardware_type

    @property
    def default_port(self):
        return self._default_port

    @property
    def hardware_type(self):
        return self._hardware_type

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

    def validate(self, node):
        """Validate node record supplied by a user.

        :param node: node record before convert()
        :raises: exception.InvalidNode
        """
        missing = []
        for field in self._mandatory_fields:
            if not node.get(field):
                missing.append(field)

        if missing:
            raise exception.InvalidNode(
                'The following fields are missing: %s' % ', '.join(missing))


class PrefixedDriverInfo(DriverInfo):
    def __init__(self, prefix, deprecated_mapping=None,
                 has_port=False, address_field='address',
                 default_port=None, hardware_type=None,
                 mandatory_fields=None):
        mapping = {
            'pm_addr': '%s_%s' % (prefix, address_field),
            'pm_user': '%s_username' % prefix,
            'pm_password': '%s_password' % prefix,
        }
        mandatory_fields = mandatory_fields or list(mapping)

        if has_port:
            mapping['pm_port'] = '%s_port' % prefix
        self._has_port = has_port

        super(PrefixedDriverInfo, self).__init__(
            prefix, mapping,
            deprecated_mapping=deprecated_mapping,
            mandatory_fields=mandatory_fields,
            default_port=default_port,
            hardware_type=hardware_type,
        )

    def unique_id_from_fields(self, fields):
        try:
            result = fields['pm_addr']
        except KeyError:
            return

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


class RedfishDriverInfo(DriverInfo):
    def __init__(self):
        mapping = {
            'pm_addr': 'redfish_address',
            'pm_user': 'redfish_username',
            'pm_password': 'redfish_password',
            'pm_system_id': 'redfish_system_id'
        }
        mandatory_fields = ['pm_addr', 'pm_system_id']

        super(RedfishDriverInfo, self).__init__(
            'redfish', mapping,
            deprecated_mapping=None,
            mandatory_fields=mandatory_fields,
            hardware_type='redfish',
        )

    def _build_id(self, address, system):
        address = re.sub(r'https?://', '', address, count=1, flags=re.I)
        return '%s/%s' % (address.rstrip('/'), system.lstrip('/'))

    def unique_id_from_fields(self, fields):
        try:
            return self._build_id(fields['pm_addr'], fields['pm_system_id'])
        except KeyError:
            return

    def unique_id_from_node(self, node):
        try:
            return self._build_id(node.driver_info['redfish_address'],
                                  node.driver_info['redfish_system_id'])
        except KeyError:
            return


class oVirtDriverInfo(DriverInfo):
    def __init__(self):
        mapping = {
            'pm_addr': 'ovirt_address',
            'pm_user': 'ovirt_username',
            'pm_password': 'ovirt_password',
            'pm_vm_name': 'ovirt_vm_name'
        }

        super(oVirtDriverInfo, self).__init__(
            'ovirt', mapping,
            mandatory_fields=list(mapping),
            hardware_type='staging-ovirt',
        )

    def unique_id_from_fields(self, fields):
        try:
            return '%s:%s' % (fields['pm_addr'], fields['pm_vm_name'])
        except KeyError:
            return

    def unique_id_from_node(self, node):
        try:
            return '%s:%s' % (node.driver_info['ovirt_address'],
                              node.driver_info['ovirt_vm_name'])
        except KeyError:
            return


class iBootDriverInfo(PrefixedDriverInfo):
    def __init__(self):
        super(iBootDriverInfo, self).__init__(
            'iboot', has_port=True,
            deprecated_mapping={
                'pm_relay_id': 'iboot_relay_id',
            },
            hardware_type='staging-iboot',
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
    '(ipmi|.*_ipmitool)': PrefixedDriverInfo('ipmi', has_port=True,
                                             default_port=623,
                                             hardware_type='ipmi',
                                             mandatory_fields=['pm_addr']
                                             ),
    '(idrac|.*_drac)': PrefixedDriverInfo('drac', has_port=True,
                                          hardware_type='idrac'),
    '(ilo|.*_ilo)': PrefixedDriverInfo('ilo', has_port=True,
                                       hardware_type='ilo'),
    '(irmc|.*_irmc)': PrefixedDriverInfo('irmc', has_port=True,
                                         hardware_type='irmc'),
    'redfish': RedfishDriverInfo(),
    'xclarity': PrefixedDriverInfo('xclarity', has_port=True),
    # test drivers
    r'staging\-ovirt': oVirtDriverInfo(),
    r'(staging\-iboot|.*_iboot)': iBootDriverInfo(),
    r'(staging\-wol|.*wol)': DriverInfo(
        'wol',
        mapping={
            'pm_addr': 'wol_host',
            'pm_port': 'wol_port',
        },
        hardware_type='staging-wol'),
    r'(staging\-amt|.*_amt)': PrefixedDriverInfo('amt',
                                                 hardware_type='staging-amt'),
    # fake_pxe was used when no management interface was supported, now
    # manual-management is used for the same purpose
    r'(manual\-management|fake_pxe|fake_agent)': DriverInfo(
        'fake', mapping={}, hardware_type='manual-management'),
    r'^fake(|\-hardware)$': DriverInfo('fake', mapping={},
                                       hardware_type='fake-hardware'),
}


def find_driver_handler(driver):
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
    return find_driver_handler(driver)


def register_ironic_node(node, client):
    driver_info = {}
    handler = _find_node_handler(node)

    if "kernel_id" in node:
        driver_info["deploy_kernel"] = node["kernel_id"]
        driver_info["rescue_kernel"] = node["kernel_id"]
    if "ramdisk_id" in node:
        driver_info["deploy_ramdisk"] = node["ramdisk_id"]
        driver_info["rescue_ramdisk"] = node["ramdisk_id"]

    interface_fields = {field: node.pop(field)
                        for field in _KNOWN_INTERFACE_FIELDS
                        if field in node}
    resource_class = node.pop('resource_class', 'baremetal')
    if resource_class != 'baremetal':
        LOG.warning('Resource class for a new node will be set to %s, which '
                    'is different from the default "baremetal". A custom '
                    'flavor will be required to deploy on such node',
                    resource_class)

    driver_info.update(handler.convert(node))

    mapping = {'cpus': 'cpu',
               'memory_mb': 'memory',
               'local_gb': 'disk',
               'cpu_arch': 'arch',
               'root_device': 'root_device'}
    properties = {k: node[v]
                  for k, v in mapping.items()
                  if node.get(v) is not None}

    extra = {}
    platform = node.get('platform')
    if platform:
        extra = dict(tripleo_platform=platform)

    if 'capabilities' in node:
        caps = capabilities_to_dict(node['capabilities'])
    else:
        caps = {}

    if 'profile' in node:
        caps['profile'] = node['profile']

    if caps:
        properties["capabilities"] = dict_to_capabilities(caps)

    driver = node['pm_type']
    if handler.hardware_type and handler.hardware_type != driver:
        LOG.warning('Replacing deprecated driver %(old)s with the '
                    'hardware type %(new)s, please update your inventory',
                    {'old': driver, 'new': handler.hardware_type})
        driver = handler.hardware_type

    create_map = {"driver": driver,
                  "properties": properties,
                  "driver_info": driver_info,
                  "resource_class": resource_class}
    create_map.update(interface_fields)
    if extra:
        create_map["extra"] = extra

    for field in ('name', 'uuid'):
        if field in node:
            create_map.update({field: six.text_type(node[field])})

    conductor_group = node.get("conductor_group")
    if conductor_group:
        create_map["conductor_group"] = conductor_group
    node_id = handler.unique_id_from_fields(node)
    LOG.debug('Registering node %s with ironic.', node_id)
    ironic_node = client.node.create(**create_map)

    for port in node.get('ports', []):
        LOG.debug('Creating Bare Metal port for node: %s, with properties: %s.'
                  % (ironic_node.uuid, port))
        client.port.create(
            address=port.get('address'),
            physical_network=port.get('physical_network', 'ctlplane'),
            local_link_connection=port.get('local_link_connection'),
            node_uuid=ironic_node.uuid)

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

        handler = find_driver_handler(node.driver)
        unique_id = handler.unique_id_from_node(node)
        if unique_id:
            node_map['pm_addr'][unique_id] = node.uuid

        node_map['uuids'].add(node.uuid)

    return node_map


def _get_node_id(node, handler, node_map):
    candidates = set()
    for port in node.get('ports', []):
        try:
            candidates.add(node_map['mac'][port['address'].lower()])
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


_NON_DRIVER_FIELDS = {'cpu': '/properties/cpus',
                      'memory': '/properties/memory_mb',
                      'disk': '/properties/local_gb',
                      'arch': '/properties/cpu_arch',
                      'root_device': '/properties/root_device',
                      'name': '/name',
                      'resource_class': '/resource_class',
                      'kernel_id': ['/driver_info/deploy_kernel',
                                    '/driver_info/rescue_kernel'],
                      'ramdisk_id': ['/driver_info/deploy_ramdisk',
                                     '/driver_info/rescue_ramdisk'],
                      'platform': '/extra/tripleo_platform',
                      'conductor_group': '/conductor_group',
                      }

_NON_DRIVER_FIELDS.update({field: '/%s' % field
                           for field in _KNOWN_INTERFACE_FIELDS})


def _update_or_register_ironic_node(node, node_map, client):
    handler = _find_node_handler(node)
    node_uuid = _get_node_id(node, handler, node_map)

    if node_uuid:
        LOG.info('Node %s already registered, updating details.',
                 node_uuid)

        patched = {}
        for field, paths in _NON_DRIVER_FIELDS.items():
            if isinstance(paths, six.string_types):
                paths = [paths]

            if field in node:
                value = node.pop(field)
                for path in paths:
                    patched[path] = value

        if 'capabilities' in node:
            caps = capabilities_to_dict(node.pop('capabilities'))
        else:
            caps = {}

        if 'profile' in node:
            caps['profile'] = node.pop('profile')

        if caps:
            patched['/properties/capabilities'] = dict_to_capabilities(caps)

        driver_info = handler.convert(node)
        for key, value in driver_info.items():
            patched['/driver_info/%s' % key] = value

        node_patch = []
        for key, value in patched.items():
            if key == 'uuid':
                continue  # not needed during update
            node_patch.append({'path': key, 'value': value, 'op': 'add'})

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


def register_all_nodes(nodes_list, client, remove=False, glance_client=None,
                       kernel_name=None, ramdisk_name=None):
    """Register all nodes in nodes_list in the baremetal service.

    :param nodes_list: The list of nodes to register.
    :param client: An Ironic client object.
    :param remove: Should nodes not in the list be removed?
    :param glance_client: A Glance client object, for fetching ramdisk images.
    :param kernel_name: Glance ID of the kernel to use for the nodes.
    :param ramdisk_name: Glance ID of the ramdisk to use for the nodes.
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

    return seen


# These fields are treated specially during enrolling/updating
_SPECIAL_NON_DRIVER_FIELDS = {'ports', 'pm_type', 'capabilities'}


def validate_nodes(nodes_list):
    """Validate all nodes list.

    :param nodes_list: The list of nodes to register.
    :raises: InvalidNode on one or more invalid nodes
    """
    failures = []
    unique_ids = set()
    names = set()
    macs = set()
    for index, node in enumerate(nodes_list):
        # Remove any comment
        node.pop("_comment", None)

        handler = _find_node_handler(node)

        try:
            handler.validate(node)
        except exception.InvalidNode as exc:
            failures.append((index, exc))

        for port in node.get('ports', ()):
            if not netutils.is_valid_mac(port['address']):
                failures.append((index, 'MAC address %s is invalid' %
                                 port['address']))

            if port['address'] in macs:
                failures.append(
                    (index, 'MAC %s is not unique' % port['address']))
            else:
                macs.add(port['address'])

        unique_id = handler.unique_id_from_fields(node)
        if unique_id:
            if unique_id in unique_ids:
                failures.append(
                    (index,
                     "Node identified by %s is already present" % unique_id))
            else:
                unique_ids.add(unique_id)

        if node.get('name'):
            if node['name'] in names:
                failures.append(
                    (index, 'Name "%s" is not unique' % node['name']))
            else:
                names.add(node['name'])

        if node.get('platform') and not node.get('arch'):
            failures.append(
                (index,
                 'You have specified a platform without an architecture'))

        try:
            capabilities_to_dict(node.get('capabilities'))
        except (ValueError, TypeError):
            failures.append(
                (index, 'Invalid capabilities: %s' % node.get('capabilities')))

        if node.get('root_device') is not None:
            if not isinstance(node['root_device'], dict):
                failures.append(
                    (index,
                     'Invalid root device: expected dict, got %s' %
                     node['root_device']))

        for field in node:
            converted = handler.convert_key(field)
            if (converted is None and field not in _NON_DRIVER_FIELDS and
                    field not in _SPECIAL_NON_DRIVER_FIELDS):
                failures.append((index, 'Unknown field %s' % field))

    if failures:
        raise exception.InvalidNode(
            '\n'.join('node #%d: %s' % tpl for tpl in failures))


def dict_to_capabilities(caps_dict):
    """Convert a dictionary into a string with the capabilities syntax."""
    if isinstance(caps_dict, six.string_types):
        return caps_dict

    # NOTE(dtantsur): sort capabilities so that their order does not change
    # between updates.
    items = sorted(caps_dict.items(), key=lambda tpl: tpl[0])
    return ','.join(["%s:%s" % (key, value)
                     for key, value in items
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


def generate_hostmap(baremetal_client, compute_client):
    """Create a map between Compute nodes and Baremetal nodes"""
    hostmap = {}
    for node in compute_client.servers.list():
        try:
            bm_node = baremetal_client.node.get_by_instance_uuid(node.id)
            for port in baremetal_client.port.list(node=bm_node.uuid):
                hostmap[port.address] = {"compute_name": node.name,
                                         "baremetal_name": bm_node.name}
        except ironicexceptions.NotFound:
            LOG.warning('Baremetal node for server %s not found - skipping it',
                        node.id)
            pass

    if hostmap == {}:
        return None
    else:
        return hostmap


def run_nova_cell_v2_discovery():
    return processutils.execute(
        '/usr/bin/sudo',
        '/bin/nova-manage',
        'cell_v2',
        'discover_hosts',
        '--verbose'
    )


def get_node_profile(node):
    """Return the profile assosicated with the node """

    capabilities = node.get('properties').get('capabilities')
    capabilities_dict = capabilities_to_dict(capabilities)

    if 'profile' in capabilities_dict:
        return capabilities_dict['profile']

    return None


def get_node_hint(node):
    """Return the 'capabilities:node' hint associated with the node """

    capabilities = node.get('properties').get('capabilities')
    capabilities_dict = capabilities_to_dict(capabilities)

    if 'node' in capabilities_dict:
        return capabilities_dict['node']

    return None
