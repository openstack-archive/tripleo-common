#   Copyright 2018 Red Hat, Inc.
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

from unittest import mock

from tripleo_common.tests import base
from tripleo_common import update


class TestUpdate(base.TestCase):

    def setUp(self):
        super(TestUpdate, self).setUp()

    def test_successful_search_stack(self):
        test_stack = [{'one': {'one_1': 'nope'}},
                      {'two': [{'two_1': {'two_1_2': 'nope'}},
                               {'two_2': [{'two_2_1': 'nope'},
                                          {'two_2_2': 'nope'}]}]},
                      {'three': [{'three_1': {'three_1_2': 'nope'}},
                                 {'three_2': [{'three_2_1': 'nope'},
                                              {'three_2_2': {
                                                  'target': ['val1', 'val2',
                                                             'val3']}}]}]}]
        result = update.search_stack(test_stack, 'target')
        self.assertEqual(['val1', 'val2', 'val3'], result)

    def test_failed_search_stack(self):
        test_stack = [{'one': {'one_1': 'nope'}},
                      {'two': [{'two_1': {'two_1_2': 'nope'}},
                               {'two_2': [{'two_2_1': 'nope'},
                                          {'two_2_2': 'nope'}]}]},
                      {'three': [{'three_1': {'three_1_2': 'nope'}},
                                 {'three_2': [{'three_2_1': 'nope'},
                                              {'three_2_2': {
                                                  'target': ['val1', 'val2',
                                                             'val3']}}]}]}]
        result = update.search_stack(test_stack, 'missing-target')
        self.assertIsNone(result)

    def test_exclusive_neutron_drivers_not_found(self):
        self.assertIsNone(
            update.get_exclusive_neutron_driver(None))
        self.assertIsNone(
            update.get_exclusive_neutron_driver('sriovnicswitch'))
        self.assertIsNone(
            update.get_exclusive_neutron_driver(['sriovnicswitch']))

    def test_exclusive_neutron_drivers_found(self):
        for ex in ['ovn', ['ovn'], ['ovn'], ['sriovnicswitch', 'ovn']]:
            self.assertEqual('ovn',
                             update.get_exclusive_neutron_driver(ex))
        for ex in ['openvswitch', ['openvswitch'],
                   ['sriovnicswitch', 'openvswitch']]:
            self.assertEqual('openvswitch',
                             update.get_exclusive_neutron_driver(ex))

    @mock.patch('tripleo_common.update.search_stack',
                autospec=True)
    def test_update_check_mechanism_drivers_force_update(self,
                                                         mock_search_stack):
        env = {'parameter_defaults': {'ForceNeutronDriverUpdate': True}}
        stack = mock.Mock()
        update.check_neutron_mechanism_drivers(env, stack, None, None)
        self.assertFalse(mock_search_stack.called)

    @mock.patch('tripleo_common.update.get_exclusive_neutron_driver',
                return_value='ovn')
    @mock.patch('tripleo_common.update.search_stack',
                autospec=True)
    def test_update_check_mechanism_drivers_match_stack_env(self,
                                                            mock_search_stack,
                                                            mock_ex_driver):
        env = {'parameter_defaults': {
            'ForceNeutronDriverUpdate': False,
            'NeutronMechanismDrivers': 'ovn'
        }}
        stack = mock.Mock()
        self.assertIsNone(update.check_neutron_mechanism_drivers(
            env, stack, None, None))

    @mock.patch('tripleo_common.update.search_stack',
                return_value='openvswitch')
    def test_update_check_mechanism_drivers_mismatch_stack_env(
            self, mock_search_stack):
        env = {'parameter_defaults': {
            'ForceNeutronDriverUpdate': False
        }}
        stack = mock.Mock()
        plan_client = mock.Mock()
        plan_client.get_object.return_value = (
            0, 'parameters:\n  NeutronMechanismDrivers: {default: ovn}\n')
        self.assertIsNotNone(update.check_neutron_mechanism_drivers(
            env, stack, plan_client, None))

    @mock.patch('tripleo_common.update.search_stack',
                return_value='ovn')
    def test_update_check_mechanism_drivers_match_stack_template(
            self, mock_search_stack):
        env = {'parameter_defaults': {
            'ForceNeutronDriverUpdate': False
        }}
        stack = mock.Mock()
        plan_client = mock.Mock()
        plan_client.get_object.return_value = (
            0, 'parameters:\n  NeutronMechanismDrivers: {default: ovn}\n')
        self.assertIsNone(update.check_neutron_mechanism_drivers(
            env, stack, plan_client, None))
