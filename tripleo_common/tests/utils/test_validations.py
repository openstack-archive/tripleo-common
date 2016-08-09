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

import mock

from tripleo_common.tests import base
from tripleo_common.utils import validations


class ValidationsTest(base.TestCase):

    @mock.patch("oslo_concurrency.processutils.execute")
    def test_create_ssh_keypair(self, mock_execute):
        validations.create_ssh_keypair('/path/to/key')
        mock_execute.assert_called_once_with(
            '/usr/bin/ssh-keygen', '-t', 'rsa', '-N', '',
            '-f', '/path/to/key', '-C', 'tripleo-validations')
