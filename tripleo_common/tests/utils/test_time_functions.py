# Copyright (c) 2017 Red Hat, Inc.
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
import contextlib
import datetime

from tripleo_common.tests import base
from tripleo_common.utils import time_functions


@contextlib.contextmanager
def mock_now(dt):
    """Context manager for mocking out datetime.utcnow() in unit tests.

    Example:

    with mock_now(datetime.datetime(2011, 2, 3, 10, 11)):
        assert datetime.datetime.utcnow() \
            == datetime.datetime(2011, 2, 3, 10, 11)
    """
    class MockDatetime(datetime.datetime):

        @classmethod
        def utcnow(cls):
            return dt

    real_datetime = datetime.datetime
    datetime.datetime = MockDatetime

    try:
        yield datetime.datetime
    finally:
        datetime.datetime = real_datetime


class TimeFunctionsTest(base.TestCase):

    def test_timestamp(self):
        fake_date = datetime.datetime(2017, 7, 31, 13, 0, 0)
        with mock_now(fake_date):
            self.assertEqual(time_functions.timestamp(), '20170731-130000')

    def test_epoch_formatting(self):
        self.assertEqual(
            time_functions.epoch_to_formatted_date(1000),
            '1970-01-01 00:00:01')

        self.assertEqual(
            time_functions.epoch_to_formatted_date(1000 * 60),
            '1970-01-01 00:01:00')

        self.assertEqual(
            time_functions.epoch_to_formatted_date(1000 * 60 * 60 * 24),
            '1970-01-02 00:00:00')

        self.assertEqual(
            time_functions.epoch_to_formatted_date(1000.0),
            '1970-01-01 00:00:01')

        self.assertEqual(
            time_functions.epoch_to_formatted_date('1000'),
            '1970-01-01 00:00:01')

        self.assertRaises(
            ValueError,
            time_functions.epoch_to_formatted_date,
            'abc')

        self.assertRaises(
            TypeError,
            time_functions.epoch_to_formatted_date,
            None)
