#   Copyright 2015 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#

import mock


FAKE_STACK = {
    'parameters': {
        'ControllerCount': 1,
        'ComputeCount': 1,
        'ObjectStorageCount': 0,
        'BlockStorageCount': 0,
        'CephStorageCount': 0,
    },
    'stack_name': 'overcloud',
    'stack_status': "CREATE_COMPLETE",
    'outputs': [
        {'output_key': 'RoleConfig',
         'output_value': {
             'foo_config': 'foo'}},
        {'output_key': 'RoleData',
         'output_value': {
             'FakeCompute': {
                 'config_settings': {'nova::compute::libvirt::services::'
                                     'libvirt_virt_type': 'qemu'},
                 'global_config_settings': {},
                 'logging_groups': ['root', 'neutron', 'nova'],
                 'logging_sources': [{'path': '/var/log/nova/nova-compute.log',
                                     'type': 'tail'}],
                 'monitoring_subscriptions': ['overcloud-nova-compute'],
                 'service_config_settings': {'horizon': {'neutron::'
                                                         'plugins': ['ovs']}
                                             },
                 'service_metadata_settings': None,
                 'service_names': ['nova_compute', 'fake_service'],
                 'step_config': ['include ::tripleo::profile::base::sshd',
                                 'include ::timezone'],
                 'upgrade_batch_tasks': [],
                 'upgrade_tasks': [{'name': 'Stop fake service',
                                    'service': 'name=fake state=stopped',
                                    'when': ['nova_api_enabled.rc == 0',
                                             'httpd_enabled.rc != 0',
                                             'step|int == 1']},
                                   {'name': 'Stop nova-compute service',
                                    'service': 'name=openstack-nova-compute '
                                               'state=stopped',
                                    'when': ['nova_compute_enabled.rc == 0',
                                             'step|int == 2', 'existing',
                                             'list']}]
                 },
             'FakeController': {
                 'config_settings': {'tripleo::haproxy::user': 'admin'},
                 'global_config_settings': {},
                 'logging_groups': ['root', 'keystone', 'neutron'],
                 'logging_sources': [{'path': '/var/log/keystone/keystone.log',
                                     'type': 'tail'}],
                 'monitoring_subscriptions': ['overcloud-keystone'],
                 'service_config_settings': {'horizon': {'neutron::'
                                                         'plugins': ['ovs']}
                                             },
                 'service_metadata_settings': None,
                 'service_names': ['pacemaker', 'fake_service'],
                 'step_config': ['include ::tripleo::profile::base::sshd',
                                 'include ::timezone'],
                 'upgrade_batch_tasks': [],
                 'upgrade_tasks': [{'name': 'Stop fake service',
                                    'service': 'name=fake state=stopped',
                                    'when': 'step|int == 1'}]}}}]}


def create_to_dict_mock(**kwargs):
    mock_with_to_dict = mock.Mock()
    mock_with_to_dict.configure_mock(**kwargs)
    mock_with_to_dict.to_dict.return_value = kwargs
    return mock_with_to_dict


def create_tht_stack(**kwargs):
    stack = FAKE_STACK.copy()
    stack.update(kwargs)
    return create_to_dict_mock(**stack)
