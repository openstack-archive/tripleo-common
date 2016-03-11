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
import tempfile

from glanceclient import exc as exceptions
import mock
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
        message = "Kernel image not found in Glance, and no path specified."
        with testtools.ExpectedException(ValueError, message):
            glance.create_or_find_kernel_and_ramdisk(client, 'bm-kernel',
                                                     None)

    def test_raise_exception_ramdisk(self):
        client = mock.MagicMock()
        client.images.find.side_effect = (self.image('aaa'),
                                          exceptions.NotFound)
        message = "Ramdisk image not found in Glance, and no path specified."
        with testtools.ExpectedException(ValueError, message):
            glance.create_or_find_kernel_and_ramdisk(client, 'bm-kernel',
                                                     'bm-ramdisk')

    def test_skip_missing_no_kernel(self):
        client = mock.MagicMock()
        client.images.find.side_effect = (exceptions.NotFound,
                                          self.image('bbb'))
        expected = {'kernel': None, 'ramdisk': 'bbb'}
        ids = glance.create_or_find_kernel_and_ramdisk(
            client, 'bm-kernel', 'bm-ramdisk', skip_missing=True)
        self.assertEqual(ids, expected)

    def test_skip_missing_no_ramdisk(self):
        client = mock.MagicMock()
        client.images.find.side_effect = (self.image('aaa'),
                                          exceptions.NotFound)
        expected = {'kernel': 'aaa', 'ramdisk': None}
        ids = glance.create_or_find_kernel_and_ramdisk(
            client, 'bm-kernel', 'bm-ramdisk', skip_missing=True)
        self.assertEqual(ids, expected)

    def test_skip_missing_kernel_and_ramdisk(self):
        client = mock.MagicMock()
        client.images.find.side_effect = exceptions.NotFound
        expected = {'kernel': None, 'ramdisk': None}
        ids = glance.create_or_find_kernel_and_ramdisk(
            client, 'bm-kernel', 'bm-ramdisk', skip_missing=True)
        self.assertEqual(ids, expected)

    def test_create_kernel_and_ramdisk(self):
        client = mock.MagicMock()
        client.images.find.side_effect = exceptions.NotFound
        client.images.create.side_effect = (self.image('aaa'),
                                            self.image('zzz'))
        expected = {'kernel': 'aaa', 'ramdisk': 'zzz'}
        with tempfile.NamedTemporaryFile() as imagefile:
            ids = glance.create_or_find_kernel_and_ramdisk(
                client, 'bm-kernel', 'bm-ramdisk', kernel_path=imagefile.name,
                ramdisk_path=imagefile.name)
        kernel_create = mock.call(name='bm-kernel', disk_format='aki',
                                  is_public=True, data=mock.ANY)
        ramdisk_create = mock.call(name='bm-ramdisk', disk_format='ari',
                                   is_public=True, data=mock.ANY)
        client.images.create.assert_has_calls([kernel_create, ramdisk_create])
        self.assertEqual(expected, ids)
