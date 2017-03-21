#   Copyright 2017 Red Hat, Inc.
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


import mock
import os
import six
import subprocess

from tripleo_common.image import kolla_builder as kb
from tripleo_common.tests import base


filedata = six.u(
    """container_images:
    - imagename: tripleoupstream/heat-docker-agents-centos:latest
      push_destination: localhost:8787
    - imagename: tripleoupstream/centos-binary-nova-compute:liberty
      uploader: docker
      pull_source: docker.io
      push_destination: localhost:8787
    - imagename: tripleoupstream/centos-binary-nova-libvirt:liberty
      uploader: docker
      pull_source: docker.io
""")


class TestKollaImageBuilder(base.TestCase):

    def setUp(self):
        super(TestKollaImageBuilder, self).setUp()
        files = []
        files.append('testfile')
        self.filelist = files

    def test_imagename_to_regex(self):
        itr = kb.KollaImageBuilder.imagename_to_regex
        self.assertIsNone(itr(''))
        self.assertIsNone(itr(None))
        self.assertEqual('foo', itr('foo'))
        self.assertEqual('foo', itr('foo:latest'))
        self.assertEqual('foo', itr('tripleo/foo:latest'))
        self.assertEqual('foo', itr('tripleo/foo'))
        self.assertEqual('foo', itr('tripleo/centos-binary-foo:latest'))
        self.assertEqual('foo', itr('centos-binary-foo:latest'))
        self.assertEqual('foo', itr('centos-binary-foo'))

    @mock.patch('tripleo_common.image.base.open',
                mock.mock_open(read_data=filedata), create=True)
    @mock.patch('os.path.isfile', return_value=True)
    @mock.patch('subprocess.Popen')
    def test_build_images(self, mock_popen, mock_path):
        process = mock.Mock()
        process.returncode = 0
        mock_popen.return_value = process

        builder = kb.KollaImageBuilder(self.filelist)
        builder.build_images(['kolla-config.conf'])
        env = os.environ.copy()
        mock_popen.assert_called_once_with([
            'kolla-build',
            '--config-file',
            'kolla-config.conf',
            'nova-compute',
            'nova-libvirt',
            'heat-docker-agents-centos',
        ], env=env)

    @mock.patch('subprocess.Popen')
    def test_build_images_no_conf(self, mock_popen):
        process = mock.Mock()
        process.returncode = 0
        mock_popen.return_value = process

        builder = kb.KollaImageBuilder([])
        builder.build_images([])
        env = os.environ.copy()
        mock_popen.assert_called_once_with([
            'kolla-build',
        ], env=env)

    @mock.patch('subprocess.Popen')
    def test_build_images_fail(self, mock_popen):
        process = mock.Mock()
        process.returncode = 1
        mock_popen.return_value = process

        builder = kb.KollaImageBuilder([])
        self.assertRaises(subprocess.CalledProcessError,
                          builder.build_images,
                          [])
        env = os.environ.copy()
        mock_popen.assert_called_once_with([
            'kolla-build',
        ], env=env)
