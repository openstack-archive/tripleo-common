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

from tripleo_common import exception
from tripleo_common.utils import nodes


FLAVOR_ROLE_EXCEPTIONS = {
    'object-storage': 'swift-storage'
}

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
        # The flavor's capabilities:profile and the role must match,
        # unless the role has a different profile name (as defined in
        # FLAVOR_ROLE_EXCEPTIONS).
        if (flavor.get_keys().get('capabilities:profile') ==
                FLAVOR_ROLE_EXCEPTIONS.get(role, role)):
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


def get_profile_of_flavor(flavor_name, compute_client):
    """Returns profile name for a given flavor name.

    :param flavor_name: Flavor name
    :param compute_client: Compute client object
    :raises: exception.DeriveParamsError: Derive parameters error

    :return: profile name
    """

    try:
        flavor = compute_client.flavors.find(name=flavor_name)
    except Exception as err:
        raise exception.DeriveParamsError(
            'Unable to determine flavor for flavor name: '
            '%(flavor_name)s. Error:%(err)s' % {'flavor_name': flavor_name,
                                                'err': err})
    if flavor:
        profile = flavor.get_keys().get('capabilities:profile', '')
        if profile:
            return profile
        else:
            raise exception.DeriveParamsError(
                'Unable to determine profile for flavor (flavor name: '
                '%s)' % flavor_name)
    else:
        raise exception.DeriveParamsError(
            'Unable to determine flavor for flavor name: '
            '%s' % flavor_name)


def convert_docker_params(stack_env=None):
    """Convert Docker* params to "Container" varients for compatibility.

    """

    if stack_env:
        pd = stack_env.get('parameter_defaults', {})
        for k, v in pd.copy().items():
            if k.startswith('Docker') and k.endswith('Image'):
                name = "Container%s" % k[6:]
                pd.setdefault(name, v)
        # TODO(dprince) add other Docker* conversions here once
        # this is wired in
