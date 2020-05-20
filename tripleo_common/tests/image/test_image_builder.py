#   Copyright 2015 Red Hat, Inc.
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

import subprocess
from unittest import mock

from tripleo_common.image.exception import ImageBuilderException
from tripleo_common.image.image_builder import DibImageBuilder
from tripleo_common.image.image_builder import ImageBuilder
from tripleo_common.tests import base


class TestImageBuilder(base.TestCase):

    def test_get_builder_dib(self):
        builder = ImageBuilder.get_builder('dib')
        assert isinstance(builder, DibImageBuilder)

    def test_get_builder_unknown(self):
        self.assertRaises(ImageBuilderException, ImageBuilder.get_builder,
                          'unknown')


class TestDibImageBuilder(base.TestCase):

    def setUp(self):
        super(TestDibImageBuilder, self).setUp()
        self.builder = DibImageBuilder()

    @mock.patch('tripleo_common.image.image_builder.open',
                create=True)
    @mock.patch('subprocess.Popen')
    def test_build_image(self, mock_popen, mock_open):
        mock_process = mock.Mock()
        mock_process.stdout.readline.side_effect = ['foo\n', 'bar\n', '']
        mock_process.poll.side_effect = [0, 0, 1]
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        mock_open.return_value = mock.MagicMock()
        mock_file = mock.Mock()
        mock_open.return_value.__enter__.return_value = mock_file
        self.builder.logger = mock.Mock()
        self.builder.build_image('image/path', 'imgtype', 'node_dist', 'arch',
                                 ['element1', 'element2'], ['options'],
                                 ['package1', 'package2'],
                                 {'skip_base': True,
                                  'docker_target': 'docker-target'})
        mock_popen.assert_called_once_with(
            ['disk-image-create', '-a', 'arch', '-o', 'image/path',
             '-t', 'imgtype',
             '-p', 'package1,package2', 'options', '-n',
             '--docker-target', 'docker-target', 'node_dist',
             'element1', 'element2'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        mock_open.assert_called_once_with(
            'image/path.log', 'w', encoding='utf-8')
        self.assertEqual([mock.call(u'foo\n'),
                          mock.call(u'bar\n')],
                         mock_file.write.mock_calls)
        self.builder.logger.info.assert_has_calls([mock.call(u'foo'),
                                                   mock.call(u'bar')])

    @mock.patch('tripleo_common.image.image_builder.open',
                create=True)
    @mock.patch('subprocess.Popen')
    def test_build_image_fails(self, mock_popen, mock_open):
        mock_process = mock.Mock()
        mock_process.stdout.readline.side_effect = ['error\n', '']
        mock_process.poll.side_effect = [0, 1]
        mock_process.returncode = 1
        mock_popen.return_value = mock_process
        mock_open.return_value = mock.MagicMock()
        mock_file = mock.Mock()
        mock_open.return_value.__enter__.return_value = mock_file
        self.builder.logger = mock.Mock()
        self.assertRaises(subprocess.CalledProcessError,
                          self.builder.build_image,
                          'image/path', 'imgtype', 'node_dist', 'arch',
                          ['element1', 'element2'], ['options'],
                          ['package1', 'package2'],
                          {'skip_base': True,
                           'docker_target': 'docker-target'})
        mock_popen.assert_called_once_with(
            ['disk-image-create', '-a', 'arch', '-o', 'image/path',
             '-t', 'imgtype',
             '-p', 'package1,package2', 'options', '-n',
             '--docker-target', 'docker-target', 'node_dist',
             'element1', 'element2'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        mock_open.assert_called_once_with(
            'image/path.log', 'w', encoding='utf-8')
        self.assertEqual([mock.call(u'error\n')],
                         mock_file.write.mock_calls)
        self.builder.logger.info.assert_has_calls([mock.call(u'error')])
