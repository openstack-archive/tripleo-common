# Copyright 2016 Red Hat, Inc.
# All Rights Reserved.
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

from tripleo_common.utils import nodes


PARAM_EXCEPTIONS = {
    'control': {
        'count': 'ControllerCount',
        'flavor': 'OvercloudControlFlavor'
    },
    'object-storage': {
        'count': 'ObjectStorageCount',
        'flavor': 'OvercloudSwiftStorageFlavor'
    }
}


def get_node_count(role, baremetal_client):
    count = 0
    for n in baremetal_client.node.list():
        node = baremetal_client.node.get(n.uuid)
        caps = nodes.capabilities_to_dict(node.properties['capabilities'])

        if caps.get('profile') == role:
            count += 1
    return count


def get_flavor(role, compute_client):
    for f in compute_client.flavors.list():
        flavor = compute_client.flavors.get(f.id)
        if flavor.get_keys().get('capabilities:profile') == role:
            return flavor.name
    return 'baremetal'


def _get_count_key(role):
    return '%sCount' % role.title().replace('-', '')


def _get_flavor_key(role):
    return 'Overcloud%sFlavor' % role.title().replace('-', '')


def set_count_and_flavor_params(role, baremetal_client, compute_client):
    """Returns the parameters for role count and flavor.

    The parameter names are derived from the role name:

        <camel case role name, no hyphens>Count
        Overcloud<camel case role name, no hyphens>Flavor

    Exceptions from this rule (the control and object-storage roles) are
    defined in the PARAM_EXCEPTIONS dict.
    """
    node_count = get_node_count(role, baremetal_client)

    if node_count == 0:
        flavor = 'baremetal'
    else:
        flavor = get_flavor(role, compute_client)

    if role in PARAM_EXCEPTIONS:
        return {
            PARAM_EXCEPTIONS[role]['count']: node_count,
            PARAM_EXCEPTIONS[role]['flavor']: flavor
        }
    return {
        _get_count_key(role): node_count,
        _get_flavor_key(role): flavor
    }
