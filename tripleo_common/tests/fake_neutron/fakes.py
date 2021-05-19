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

from tripleo_common.tests.fake_neutron import stubs


ctlplane_network = stubs.FakeNeutronNetwork(
    name='ctlplane',
    id='ctlplane_network_id',
    mtu=1500,
    dns_domain='ctlplane.example.com.',
    subnet_ids=['ctlplane_subnet_id'],
    tags=[],
)
internal_api_network = stubs.FakeNeutronNetwork(
    name='internal_api',
    id='internal_api_network_id',
    mtu=1500,
    dns_domain='internalapi.example.com.',
    subnet_ids=['internal_api_subnet_id'],
    tags=['tripleo_net_idx=0',
          'tripleo_vip=true',
          'tripleo_network_name=InternalApi'],
)

ctlplane_subnet = stubs.FakeNeutronSubnet(
    name='ctlplane-subnet',
    id='ctlplane_subnet_id',
    network_id='ctlplane_network_id',
    cidr='192.0.2.0/24',
    gateway_ip='192.0.2.1',
    dns_nameservers=['192.0.2.253', '192.0.2.254'],
    host_routes=[],
    ip_version=4,
    tags=[],
)
internal_api_subnet = stubs.FakeNeutronSubnet(
    name='internal_api_subnet',
    id='internal_api_subnet_id',
    network_id='internal_api_network_id',
    cidr='198.51.100.128/25',
    gateway_ip='198.51.100.129',
    dns_nameservers=[],
    host_routes=[],
    ip_version=4,
    tags=['tripleo_vlan_id=20'],
)


fake_networks = [ctlplane_network, internal_api_network]
fake_subnets = [ctlplane_subnet, internal_api_subnet]

controller0_ports = [
    stubs.FakeNeutronPort(name='c-0-ctlplane',
                          id='controller_0_ctlplane_id',
                          network_id=ctlplane_network.id,
                          fixed_ips=[dict(ip_address='192.0.2.10',
                                          subnet_id=ctlplane_subnet.id)],
                          dns_name='c-0',
                          tags=['tripleo_network_name=ctlplane',
                                'tripleo_role=Controller',
                                'tripleo_stack=overcloud',
                                'tripleo_default_route=True'],
                          ),
    stubs.FakeNeutronPort(name='c-0-internal_api',
                          id='controller_0_internal_api_id',
                          network_id=internal_api_network.id,
                          fixed_ips=[dict(ip_address='198.51.100.140',
                                          subnet_id=internal_api_subnet.id)],
                          dns_name='c-0',
                          tags=['tripleo_network_name=InternalApi',
                                'tripleo_role=Controller',
                                'tripleo_stack=overcloud',
                                'tripleo_default_route=False'],
                          ),
]

controller1_ports = [
    stubs.FakeNeutronPort(name='c-1-ctlplane',
                          id='controller_1_ctlplane_id',
                          network_id=ctlplane_network.id,
                          fixed_ips=[dict(ip_address='192.0.2.11',
                                          subnet_id=ctlplane_subnet.id)],
                          dns_name='c-1',
                          tags=['tripleo_network_name=ctlplane',
                                'tripleo_role=Controller',
                                'tripleo_stack=overcloud',
                                'tripleo_default_route=True'],
                          ),
    stubs.FakeNeutronPort(name='c-1-internal_api',
                          id='controller_1_internal_api_id',
                          network_id=internal_api_network.id,
                          fixed_ips=[dict(ip_address='198.51.100.141',
                                          subnet_id=internal_api_subnet.id)],
                          dns_name='c-1',
                          tags=['tripleo_network_name=InternalApi',
                                'tripleo_role=Controller',
                                'tripleo_stack=overcloud',
                                'tripleo_default_route=False'],
                          ),
]

controller2_ports = [
    stubs.FakeNeutronPort(name='c-2-ctlplane',
                          id='controller_2_ctlplane_id',
                          network_id=ctlplane_network.id,
                          fixed_ips=[dict(ip_address='192.0.2.12',
                                          subnet_id=ctlplane_subnet.id)],
                          dns_name='c-2',
                          tags=['tripleo_network_name=ctlplane',
                                'tripleo_role=Controller',
                                'tripleo_stack=overcloud',
                                'tripleo_default_route=True'],
                          ),
    stubs.FakeNeutronPort(name='c-2-internal_api',
                          id='controller_2_internal_api_id',
                          network_id=internal_api_network.id,
                          fixed_ips=[dict(ip_address='198.51.100.142',
                                          subnet_id=internal_api_subnet.id)],
                          dns_name='c-2',
                          tags=['tripleo_network_name=InternalApi',
                                'tripleo_role=Controller',
                                'tripleo_stack=overcloud',
                                'tripleo_default_route=False'],
                          ),
]

compute_0_ports = [
    stubs.FakeNeutronPort(name='cp-0-ctlplane',
                          id='compute_0_ctlplane_id',
                          network_id=ctlplane_network.id,
                          fixed_ips=[dict(ip_address='192.0.2.20',
                                          subnet_id=ctlplane_subnet.id)],
                          dns_name='cp-0',
                          tags=['tripleo_network_name=ctlplane',
                                'tripleo_role=Compute',
                                'tripleo_stack=overcloud',
                                'tripleo_default_route=True'],
                          ),
    stubs.FakeNeutronPort(name='cp-0-internal_api',
                          id='compute_0_internal_api_id',
                          network_id=internal_api_network.id,
                          fixed_ips=[dict(ip_address='198.51.100.150',
                                          subnet_id=internal_api_subnet.id)],
                          dns_name='cp-0',
                          tags=['tripleo_network_name=InternalApi',
                                'tripleo_role=Compute',
                                'tripleo_stack=overcloud',
                                'tripleo_default_route=False'],
                          ),

]

custom_0_ports = [
    stubs.FakeNeutronPort(name='cs-0-ctlplane',
                          id='custom_0_ctlplane_id',
                          network_id=ctlplane_network.id,
                          fixed_ips=[dict(ip_address='192.0.2.200',
                                          subnet_id=ctlplane_subnet.id)],
                          dns_name='cs-0',
                          tags=['tripleo_network_name=ctlplane',
                                'tripleo_role=CustomRole',
                                'tripleo_stack=overcloud',
                                'tripleo_default_route=True'],
                          ),
]
