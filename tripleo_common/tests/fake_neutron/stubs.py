# Copyright 2020 Red Hat, Inc.
# All Rights Reserved.
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

class FakeNeutronNetwork(dict):
    def __init__(self, **attrs):
        NETWORK_ATTRS = ['id',
                         'name',
                         'status',
                         'tenant_id',
                         'is_admin_state_up',
                         'mtu',
                         'segments',
                         'is_shared',
                         'subnets',
                         'provider:network_type',
                         'provider:physical_network',
                         'provider:segmentation_id',
                         'router:external',
                         'availability_zones',
                         'availability_zone_hints',
                         'is_default',
                         'tags']

        raw = dict.fromkeys(NETWORK_ATTRS)
        raw.update(attrs)
        raw.update({
            'provider_physical_network': attrs.get(
                'provider:physical_network', None),
            'provider_network_type': attrs.get(
                'provider:network_type', None),
            'provider_segmentation_id': attrs.get(
                'provider:segmentation_id', None)
        })
        super(FakeNeutronNetwork, self).__init__(raw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        if key in self:
            self[key] = value
        else:
            raise AttributeError(key)


class FakeNeutronPort(dict):
    def __init__(self, **attrs):
        PORT_ATTRS = ['admin_state_up',
                      'allowed_address_pairs',
                      'binding:host_id',
                      'binding:profile',
                      'binding:vif_details',
                      'binding:vif_type',
                      'binding:vnic_type',
                      'data_plane_status',
                      'description',
                      'device_id',
                      'device_owner',
                      'dns_assignment',
                      'dns_domain',
                      'dns_name',
                      'extra_dhcp_opts',
                      'fixed_ips',
                      'id',
                      'mac_address',
                      'name', 'network_id',
                      'port_security_enabled',
                      'security_group_ids',
                      'status',
                      'tenant_id',
                      'qos_network_policy_id',
                      'qos_policy_id',
                      'tags',
                      'uplink_status_propagation']

        raw = dict.fromkeys(PORT_ATTRS)
        raw.update(attrs)
        super(FakeNeutronPort, self).__init__(raw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        if key in self:
            self[key] = value
        else:
            raise AttributeError(key)


class FakeNeutronSubnet(dict):
    def __init__(self, **attrs):
        SUBNET_ATTRS = ['id',
                        'name',
                        'network_id',
                        'cidr',
                        'tenant_id',
                        'is_dhcp_enabled',
                        'dns_nameservers',
                        'allocation_pools',
                        'host_routes',
                        'ip_version',
                        'gateway_ip',
                        'ipv6_address_mode',
                        'ipv6_ra_mode',
                        'subnetpool_id',
                        'segment_id',
                        'tags']

        raw = dict.fromkeys(SUBNET_ATTRS)
        raw.update(attrs)
        super(FakeNeutronSubnet, self).__init__(raw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        if key in self:
            self[key] = value
        else:
            raise AttributeError(key)
