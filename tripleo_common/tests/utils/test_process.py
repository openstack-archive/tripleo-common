# Copyright (c) 2019 Red Hat, Inc.
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

"""Unit tests for utils.process."""


import os

import mock
from oslo_concurrency import processutils

from tripleo_common.tests import base
from tripleo_common.utils import process


class ExecuteTestCase(base.TestCase):
    # Allow calls to process.execute() and related functions
    block_execute = False

    @mock.patch.object(processutils, 'execute', autospec=True)
    @mock.patch.object(os.environ, 'copy', return_value={}, autospec=True)
    def test_execute_use_standard_locale_no_env_variables(self, env_mock,
                                                          execute_mock):
        process.execute('foo', use_standard_locale=True)
        execute_mock.assert_called_once_with('foo',
                                             env_variables={'LC_ALL': 'C'})

    @mock.patch.object(processutils, 'execute', autospec=True)
    def test_execute_use_standard_locale_with_env_variables(self,
                                                            execute_mock):
        process.execute('foo', use_standard_locale=True,
                        env_variables={'foo': 'bar'})
        execute_mock.assert_called_once_with('foo',
                                             env_variables={'LC_ALL': 'C',
                                                            'foo': 'bar'})

    @mock.patch.object(processutils, 'execute', autospec=True)
    def test_execute_not_use_standard_locale(self, execute_mock):
        process.execute('foo', use_standard_locale=False,
                        env_variables={'foo': 'bar'})
        execute_mock.assert_called_once_with('foo',
                                             env_variables={'foo': 'bar'})

    @mock.patch.object(process, 'LOG', autospec=True)
    def _test_execute_with_log_stdout(self, log_mock, log_stdout=None):
        with mock.patch.object(
                processutils, 'execute', autospec=True) as execute_mock:
            execute_mock.return_value = ('stdout', 'stderr')
            if log_stdout is not None:
                process.execute('foo', log_stdout=log_stdout)
            else:
                process.execute('foo')
            execute_mock.assert_called_once_with('foo')
            name, args, kwargs = log_mock.debug.mock_calls[1]
            if log_stdout is False:
                self.assertEqual(2, log_mock.debug.call_count)
                self.assertNotIn('stdout', args[0])
            else:
                self.assertEqual(3, log_mock.debug.call_count)
                self.assertIn('stdout', args[0])

    def test_execute_with_log_stdout_default(self):
        self._test_execute_with_log_stdout()

    def test_execute_with_log_stdout_true(self):
        self._test_execute_with_log_stdout(log_stdout=True)

    def test_execute_with_log_stdout_false(self):
        self._test_execute_with_log_stdout(log_stdout=False)
