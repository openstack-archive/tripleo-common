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

from tripleo_common.image.base import BaseImageManager
from tripleo_common.image.exception import ImageSpecificationException
from tripleo_common.tests import base as testbase
from tripleo_common.tests.image import fakes


class TestBaseImageManager(testbase.TestCase):
    def setUp(self):
        super(TestBaseImageManager, self).setUp()

    @mock.patch('yaml.load', autospec=True)
    @mock.patch('os.path.isfile', autospec=True)
    def test_load_config_files(self, mock_os_path_isfile, mock_yaml_load):
        mock_yaml_load.return_value = fakes.create_disk_images()

        mock_os_path_isfile.return_value = True

        mock_open_context = mock.mock_open()
        mock_open_context().read.return_value = "YAML"

        with mock.patch('six.moves.builtins.open', mock_open_context):
            base_manager = BaseImageManager(['yamlfile'])
            disk_images = base_manager.load_config_files('disk_images')

        mock_yaml_load.assert_called_once_with("YAML")
        self.assertEqual([{
            'arch': 'amd64',
            'distro': 'some_awesome_os',
            'imagename': 'overcloud',
            'type': 'qcow2',
            'elements': ['image_element']
        }], disk_images)

    def test_load_config_files_not_found(self):
        base_manager = BaseImageManager(['file/does/not/exist'])
        self.assertRaises(IOError, base_manager.load_config_files,
                          'disk_images')

    @mock.patch('yaml.load', autospec=True)
    @mock.patch('os.path.isfile', autospec=True)
    def test_load_config_files_multiple_files(self, mock_os_path_isfile,
                                              mock_yaml_load):
        mock_yaml_load.side_effect = [{
            'disk_images': [{
                'arch': 'amd64',
                'imagename': 'overcloud',
                'distro': 'some_awesome_distro',
                'type': 'qcow2',
                'elements': ['image_element']
            }]},
            {
            'disk_images': [{
                'imagename': 'overcloud',
                'elements': ['another_image_element'],
                'packages': ['a_package'],
                'otherkey': 'some_other_key',
            }]}]

        mock_os_path_isfile.return_value = True

        mock_open_context = mock.mock_open()
        mock_open_context().read.return_value = "YAML"

        with mock.patch('six.moves.builtins.open', mock_open_context):
            base_manager = BaseImageManager(['yamlfile1', 'yamlfile2'])
            disk_images = base_manager.load_config_files('disk_images')

        self.assertEqual(2, mock_yaml_load.call_count)
        self.assertEqual([{
            'arch': 'amd64',
            'distro': 'some_awesome_distro',
            'imagename': 'overcloud',
            'type': 'qcow2',
            'elements': ['image_element', 'another_image_element'],
            'packages': ['a_package'],
            'otherkey': 'some_other_key',
        }], disk_images)

    @mock.patch('yaml.load', autospec=True)
    @mock.patch('os.path.isfile', autospec=True)
    def test_load_config_files_missing_image_name(self, mock_os_path_isfile,
                                                  mock_yaml_load):
        mock_yaml_load.return_value = {
            'disk_images': [{
                'arch': 'amd64',
                'imagename': 'overcloud',
                'type': 'qcow2',
                'elements': ['image_element']
            }, {
                'arch': 'amd64',
                'type': 'qcow2',
            }]
        }

        mock_os_path_isfile.return_value = True

        mock_open_context = mock.mock_open()
        mock_open_context().read.return_value = "YAML"

        with mock.patch('six.moves.builtins.open', mock_open_context):
            base_manager = BaseImageManager(['yamlfile'])
            self.assertRaises(ImageSpecificationException,
                              base_manager.load_config_files, 'disk_images')

    @mock.patch('yaml.load', autospec=True)
    @mock.patch('os.path.isfile', autospec=True)
    def test_load_config_files_single_image(self, mock_os_path_isfile,
                                            mock_yaml_load):
        mock_yaml_load.side_effect = [{
            'disk_images': [
                {
                    'arch': 'amd64',
                    'imagename': 'overcloud',
                    'distro': 'some_awesome_distro',
                    'type': 'qcow2',
                    'elements': ['image_element']
                },
                {
                    'arch': 'amd64',
                    'imagename': 'not-overcloud',
                    'distro': 'some_other_distro',
                    'type': 'qcow2',
                    'elements': ['other_element']
                }
            ]}]

        mock_os_path_isfile.return_value = True

        mock_open_context = mock.mock_open()
        mock_open_context().read.return_value = "YAML"

        with mock.patch('six.moves.builtins.open', mock_open_context):
            base_manager = BaseImageManager(['yamlfile1'],
                                            images=['not-overcloud'])
            disk_images = base_manager.load_config_files('disk_images')

        self.assertEqual(1, mock_yaml_load.call_count)
        self.assertEqual([{
            'arch': 'amd64',
            'distro': 'some_other_distro',
            'imagename': 'not-overcloud',
            'type': 'qcow2',
            'elements': ['other_element'],
        }], disk_images)
