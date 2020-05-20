# Copyright 2016 Red Hat, Inc.
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

import sys
from unittest import mock

from tripleo_common.tests import base
from tripleo_common.tests import fake_nova

# See the README file in the fake_nova module directory for details on why
# this is being done.
if 'nova' not in sys.modules:
    sys.modules['nova'] = fake_nova
else:
    raise RuntimeError('nova module already found in sys.modules.  The '
                       'fake_nova injection should be removed.')
from tripleo_common.filters import capabilities_filter  # noqa


class TestCapabilitiesFilter(base.TestCase):
    def test_no_requested_node(self):
        instance = capabilities_filter.TripleOCapabilitiesFilter()
        host_state = mock.Mock()
        host_state.stats.get.return_value = ''
        spec_obj = mock.Mock()
        spec_obj.scheduler_hints.get.return_value = []
        self.assertTrue(instance.host_passes(host_state, spec_obj))

    def test_requested_node_matches(self):
        def mock_host_get(key):
            if key == 'node':
                return 'compute-0'
            else:
                self.fail('Unexpected key requested by filter')

        def mock_spec_get(key):
            if key == 'capabilities:node':
                return ['compute-0']
            else:
                self.fail('Unexpected key requested by filter')

        instance = capabilities_filter.TripleOCapabilitiesFilter()
        host_state = mock.Mock()
        host_state.stats.get.side_effect = mock_host_get
        spec_obj = mock.Mock()
        spec_obj.scheduler_hints.get.side_effect = mock_spec_get
        self.assertTrue(instance.host_passes(host_state, spec_obj))

    def test_requested_node_no_match(self):
        instance = capabilities_filter.TripleOCapabilitiesFilter()
        host_state = mock.Mock()
        host_state.stats.get.return_value = 'controller-0'
        spec_obj = mock.Mock()
        spec_obj.scheduler_hints.get.return_value = ['compute-0']
        self.assertFalse(instance.host_passes(host_state, spec_obj))
