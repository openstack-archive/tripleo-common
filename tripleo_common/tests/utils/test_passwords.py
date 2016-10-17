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
import mock

from tripleo_common.tests import base
from tripleo_common.utils import passwords as password_utils


class TestPasswords(base.TestCase):

    def test_create_cephx_key(self):
        key = password_utils.create_cephx_key()
        self.assertEqual(len(key), 40)

    def test_get_snmpd_readonly_user_password(self):

        mock_mistral = mock.Mock()
        mock_mistral.environments.get.return_value = mock.Mock(variables={
            "undercloud_ceilometer_snmpd_password": "78cbc32b858718267c355d4"
        })

        value = password_utils.get_snmpd_readonly_user_password(mock_mistral)

        self.assertEqual(value, "78cbc32b858718267c355d4")
