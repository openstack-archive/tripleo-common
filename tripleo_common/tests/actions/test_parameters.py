# Copyright 2016 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
from unittest import mock

from tripleo_common.actions import parameters
from tripleo_common import exception
from tripleo_common.tests import base


class GetProfileOfFlavorActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.parameters.get_profile_of_flavor')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    def test_profile_found(self, mock_get_compute_client,
                           mock_get_profile_of_flavor):
        mock_ctx = mock.MagicMock()
        mock_get_profile_of_flavor.return_value = 'compute'
        action = parameters.GetProfileOfFlavorAction('oooq_compute')
        result = action.run(mock_ctx)
        expected_result = "compute"
        self.assertEqual(result, expected_result)

    @mock.patch('tripleo_common.utils.parameters.get_profile_of_flavor')
    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_compute_client')
    def test_profile_not_found(self, mock_get_compute_client,
                               mock_get_profile_of_flavor):
        mock_ctx = mock.MagicMock()
        profile = (exception.DeriveParamsError, )
        mock_get_profile_of_flavor.side_effect = profile
        action = parameters.GetProfileOfFlavorAction('no_profile')
        result = action.run(mock_ctx)
        self.assertTrue(result.is_error())
        mock_get_profile_of_flavor.assert_called_once()
