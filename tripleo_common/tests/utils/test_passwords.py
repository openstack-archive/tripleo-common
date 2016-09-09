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

    @mock.patch("subprocess.Popen")
    def test_get_hiera_key(self, mock_popen):

        process_mock = mock.Mock()
        process_mock.communicate.return_value = ["pa$$word", ""]
        mock_popen.return_value = process_mock

        value = password_utils.get_hiera_key('password_name')

        self.assertEqual(value, "pa$$word")
