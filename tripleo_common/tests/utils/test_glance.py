# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

import collections
from unittest import mock

from glanceclient import exc as exceptions
import testtools

from tripleo_common.tests import base
from tripleo_common.utils import glance


class GlanceTest(base.TestCase):

    def setUp(self):
        super(GlanceTest, self).setUp()
        self.image = collections.namedtuple('image', ['id'])

    def test_return_existing_kernel_and_ramdisk(self):
        client = mock.MagicMock()
        expected = {'kernel': 'aaa', 'ramdisk': 'zzz'}
        client.images.find.side_effect = (self.image('aaa'), self.image('zzz'))
        ids = glance.create_or_find_kernel_and_ramdisk(client, 'bm-kernel',
                                                       'bm-ramdisk')
        client.images.create.assert_not_called()
        self.assertEqual(expected, ids)

    def test_raise_exception_kernel(self):
        client = mock.MagicMock()
        client.images.find.side_effect = exceptions.NotFound
        message = "Kernel image bm-kernel not found in Glance"
        with testtools.ExpectedException(ValueError, message):
            glance.create_or_find_kernel_and_ramdisk(client, 'bm-kernel',
                                                     None)

    def test_raise_exception_ramdisk(self):
        client = mock.MagicMock()
        client.images.find.side_effect = (self.image('aaa'),
                                          exceptions.NotFound)
        message = "Ramdisk image bm-ramdisk not found in Glance"
        with testtools.ExpectedException(ValueError, message):
            glance.create_or_find_kernel_and_ramdisk(client, 'bm-kernel',
                                                     'bm-ramdisk')

    def test_return_files(self):
        client = mock.MagicMock()
        expected = {'kernel': 'file:///kernel', 'ramdisk': 'file:///ramdisk'}
        ids = glance.create_or_find_kernel_and_ramdisk(
            None, 'file:///kernel', 'file:///ramdisk')
        client.images.assert_not_called()
        self.assertEqual(expected, ids)

    def test_return_urls(self):
        client = mock.MagicMock()
        expected = {'kernel': 'http://kernel', 'ramdisk': 'http://ramdisk'}
        ids = glance.create_or_find_kernel_and_ramdisk(
            client, 'http://kernel', 'http://ramdisk')
        client.images.assert_not_called()
        self.assertEqual(expected, ids)

    def test_return_https_urls_no_client(self):
        expected = {'kernel': 'https://kernel', 'ramdisk': 'https://ramdisk'}
        ids = glance.create_or_find_kernel_and_ramdisk(
            None, 'https://kernel', 'https://ramdisk')
        self.assertEqual(expected, ids)
