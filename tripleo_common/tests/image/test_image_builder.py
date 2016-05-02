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


import mock

import six

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

    # The open method is in a different module for
    # python2 vs. python3
    if six.PY2:
        open_module = '__builtin__.open'
    else:
        open_module = 'builtins.open'

    @mock.patch(open_module)
    @mock.patch('subprocess.check_call')
    def test_build_image(self, mock_check_call, mock_open):
        self.builder.build_image('image/path', 'imgtype', 'node_dist', 'arch',
                                 ['element1', 'element2'], ['options'],
                                 ['package1', 'package2'],
                                 {'skip_base': True,
                                  'docker_target': 'docker-target'})
        mock_check_call.assert_called_once_with(
            ['disk-image-create', '-a', 'arch', '-o', 'image/path',
             '-t', 'imgtype',
             '-p', 'package1,package2', 'options', '-n',
             '--docker-target', 'docker-target', 'node_dist',
             'element1', 'element2'],
            stdout=mock.ANY,
            stderr=mock.ANY)
        mock_open.assert_called_once_with('image/path.log', 'w')
