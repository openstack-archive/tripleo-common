#!/usr/bin/env python
# Copyright (c) 2021 OpenStack Foundation
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

import ipaddress

ALLOWED_DAEMONS = ['host', 'mon', 'mgr', 'mds', 'nfs', 'osd', 'rgw', 'grafana',
                   'crash', 'prometheus', 'alertmanager', 'node-exporter',
                   'ingress']

ALLOWED_HOST_PLACEMENT_MODE = ['hosts', 'host_pattern', 'label']

CRUSH_ALLOWED_LOCATION = ['osd', 'host', 'chassis', 'rack', 'row', 'pdu',
                          'pod', 'room', 'datacenter', 'zone', 'region',
                          'root']

ALLOWED_EXTRA_KEYS = {
    'osd': [
        'data_devices',
        'db_devices',
        'wal_devices',
        'encrypted'
    ]
}

ALLOWED_SPEC_KEYS = {
    'rgw': [
        'rgw_frontend_port',
        'rgw_frontend_type',
        'rgw_realm',
        'rgw_zone',
        'rgw_ip_address',
        'rgw_frontend_ssl_certificate'
    ],
    'nfs': [
        'namespace',
        'pool'
    ],
    'ingress': [
        'backend_service',
        'frontend_port',
        'monitor_port',
        'virtual_ip',
        'virtual_interface_networks',
        'ssl_cert'
    ],
}


class CephPlacementSpec(object):
    def __init__(self,
                 hosts: list,
                 host_pattern: str,
                 count: int,
                 labels: list):

        if len(labels) > 0:
            self.labels = labels
        if count > 0:
            self.count = count
        if host_pattern is not None and len(host_pattern) > 0:
            self.host_pattern = host_pattern

        if hosts is not None and len(hosts) > 0:
            self.hosts = hosts

    def __setattr__(self, key, value):
        self.__dict__[key] = value

    def make_spec(self):
        # if the host list is passed, this should be
        # the preferred way
        if getattr(self, 'hosts', None):
            spec_template = {
                'placement': {
                    'hosts': self.hosts
                }
            }
        # if no list is passed or an empty list is provided
        # let's check if a "host pattern" is provided
        elif getattr(self, 'host_pattern', None):
            spec_template = {
                'placement': {
                    'host_pattern': self.host_pattern
                }
            }
        elif getattr(self, 'labels', None) is not None:
            spec_template = {
                'placement': {
                    'labels': self.labels
                }
            }
        else:
            spec_template = {}

        return spec_template


class CephHostSpec(object):
    def __init__(self, daemon_type: str,
                 daemon_addr: str,
                 daemon_hostname: str,
                 labels: list,
                 location: dict = None,
                 ):

        self.daemon_type = daemon_type
        self.daemon_addr = daemon_addr
        self.daemon_hostname = daemon_hostname

        assert isinstance(labels, list)
        self.labels = list(set(labels))

        # init crush location parameters
        if location and isinstance(location, dict):
            self.location = location
        else:
            self.location = {}

    def is_valid_crush_location(self):
        for k in self.location.keys():
            if k not in CRUSH_ALLOWED_LOCATION:
                return False
        return True

    def make_daemon_spec(self):
        lb = {}
        crloc = {}

        spec_template = {
            'service_type': self.daemon_type,
            'addr': self.daemon_addr,
            'hostname': self.daemon_hostname,
        }

        if len(self.labels) > 0:
            lb = {'labels': self.labels}

        if self.location:
            if self.is_valid_crush_location():
                crloc = {'location': self.location}
            else:
                raise Exception("Fatal: the spec should be "
                                "composed by only allowed keywords")

        spec_template = {**spec_template, **lb, **crloc}
        return spec_template


class CephDaemonSpec(object):
    def __init__(self, daemon_type: str,
                 daemon_id: str,
                 daemon_name: str,
                 hosts: list,
                 placement_pattern: str,
                 networks: list,
                 spec: dict,
                 labels: list,
                 **kwargs: dict):

        self.daemon_name = daemon_name
        self.daemon_id = daemon_id
        self.daemon_type = daemon_type
        self.hosts = hosts
        self.placement = placement_pattern
        self.labels = labels

        # network list where the current daemon should be bound
        if not networks:
            self.networks = []
        else:
            self.networks = networks

        # extra keywords definition (e.g. data_devices for OSD(s)
        self.extra = {}
        for k, v in kwargs.items():
            self.extra[k] = v

        assert isinstance(spec, dict)
        self.spec = spec

    def __setattr__(self, key, value):
        self.__dict__[key] = value

    def validate_networks(self):
        if len(self.networks) < 1:
            return False

        for network in self.networks:
            try:
                ipaddress.ip_network(network)
            except ValueError as e:
                raise Exception(f'Cannot parse network {network}: {e}')
        return True

    def make_daemon_spec(self):

        # the placement dict
        pl = {}
        # the spec dict
        sp = {}

        place = CephPlacementSpec(self.hosts, self.placement, 0, self.labels)
        pl = place.make_spec()

        # the spec daemon header
        spec_template = {
            'service_type': self.daemon_type,
            'service_name': self.daemon_name,
            'service_id': self.daemon_id,
        }

        # the networks dict
        ntw = {}

        if self.validate_networks():
            ntw = {
                'networks': self.networks
            }

        # process extra parameters if present
        if not self.validate_keys(self.extra.keys(), ALLOWED_EXTRA_KEYS):
            raise Exception("Fatal: the spec should be composed "
                            "by only allowed keywords")

        # append the spec if provided
        if len(self.spec.keys()) > 0:
            if self.validate_keys(self.spec.keys(), ALLOWED_SPEC_KEYS):
                sp = {'spec': self.normalize_spec(self.filter_spec(self.spec))}
            else:
                raise Exception("Fatal: the spec should be composed "
                                "by only allowed keywords")

        # build the resulting daemon template
        spec_template = {**spec_template, **ntw, **self.extra, **pl, **sp}
        return spec_template

    def normalize_spec(self, spec):
        '''
        For each spec key we need to make sure
        that ports are evaluated as int, otherwise
        cephadm fails when the spec is applied.
        '''
        for k, v in spec.items():
            if 'port' in k:
                spec[k] = int(v)
        return spec

    def filter_spec(self, spec):
        return {k: v for k, v in spec.items() if v}

    def validate_keys(self, spec, ALLOWED_KEYS):
        '''
        When the spec section is created, if constraints are
        defined for a given daemon, then this check is run
        to make sure only valid keys are provided.
        '''

        # an entry for the current daemon is not found
        # no checks are required (let ceph orch take care of
        # the validation
        if self.daemon_type not in ALLOWED_KEYS.keys():
            return True

        # a basic check on the spec dict: if some constraints
        # are specified, the provided keys should be contained
        # in the ALLOWED keys
        for item in spec:
            if item not in ALLOWED_KEYS.get(self.daemon_type):
                return False
        return True

    def log(self, msg):
        print('[DEBUG] - %s' % msg)

    def whoami(self) -> str:
        return '%s.%s' % (self.daemon_type, self.daemon_id)


def export(content, fp):
    if len(content) > 0:
        if fp is not None and len(fp) > 0:
            open(fp, 'w').close()  # reset file
            with open(fp, 'w') as f:
                f.write('---\n')
                f.write(content)
        else:
            print('---')
            print(content.rstrip('\r\n'))
    else:
        print('Nothing to dump!')
