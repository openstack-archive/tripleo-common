#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import copy

import six

from heat.engine.resources.openstack.neutron import net
from heat.engine.resources.openstack.neutron import port
from heat.engine.resources.openstack.neutron import subnet


def _copy_schema_immutable(schema):
    new_schema = copy.deepcopy(schema)
    if not schema.update_allowed:
        new_schema.immutable = True
    return new_schema


class ImmutableNet(net.Net):
    '''Ensure an existing net doesn't change.'''

    properties_schema = {
        k: _copy_schema_immutable(v)
        for k, v in six.iteritems(net.Net.properties_schema)
    }


class ImmutablePort(port.Port):
    '''Ensure an existing port doesn't change.'''

    properties_schema = {
        k: _copy_schema_immutable(v)
        for k, v in six.iteritems(port.Port.properties_schema)
    }


class ImmutableSubnet(subnet.Subnet):
    '''Ensure an existing subnet doesn't change.'''

    properties_schema = {
        k: _copy_schema_immutable(v)
        for k, v in six.iteritems(subnet.Subnet.properties_schema)
    }


def resource_mapping():
    return {
        'OS::Neutron::Net': ImmutableNet,
        'OS::Neutron::Port': ImmutablePort,
        'OS::Neutron::Subnet': ImmutableSubnet,
    }
