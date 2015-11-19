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
import operator
import six

from tripleo_common.image.exception import ImageUploaderException
from tripleo_common.image.image_uploader import DockerImageUploader
from tripleo_common.image.image_uploader import ImageUploader
from tripleo_common.image.image_uploader import ImageUploadManager
from tripleo_common.tests import base
from tripleo_common.tests.image import fakes


filedata = six.u(
    """uploads:
    - imagename: tripleoupstream/heat-docker-agents-centos:latest
      uploader: docker
      pull_source: docker.io
      push_destination: localhost:8787
    - imagename: tripleoupstream/centos-binary-nova-compute:liberty
      uploader: docker
      pull_source: docker.io
      push_destination: localhost:8787
    - imagename: tripleoupstream/centos-binary-nova-libvirt:liberty
      uploader: docker
      pull_source: docker.io
      push_destination: localhost:8787
""")


class TestImageUploadManager(base.TestCase):
    def setUp(self):
        super(TestImageUploadManager, self).setUp()
        files = []
        files.append('testfile')
        self.filelist = files

    @mock.patch('tripleo_common.image.base.open',
                mock.mock_open(read_data=filedata), create=True)
    @mock.patch('os.path.isfile', return_value=True)
    @mock.patch('tripleo_common.image.image_uploader.Client')
    def test_file_parsing(self, mockpath, mockdocker):
        print(filedata)
        manager = ImageUploadManager(self.filelist, debug=True)
        parsed_data = manager.upload()
        mockpath(self.filelist[0])

        expected_data = fakes.create_parsed_upload_images()
        sorted_expected_data = sorted(expected_data,
                                      key=operator.itemgetter('imagename'))
        sorted_parsed_data = sorted(parsed_data,
                                    key=operator.itemgetter('imagename'))
        self.assertEqual(sorted_parsed_data, sorted_expected_data)


class TestImageUploader(base.TestCase):

    def setUp(self):
        super(TestImageUploader, self).setUp()

    def test_get_uploader_docker(self):
        uploader = ImageUploader.get_uploader('docker')
        assert isinstance(uploader, DockerImageUploader)

    def test_get_builder_unknown(self):
        self.assertRaises(ImageUploaderException, ImageUploader.get_uploader,
                          'unknown')


class TestDockerImageUploader(base.TestCase):

    def setUp(self):
        super(TestDockerImageUploader, self).setUp()
        self.uploader = DockerImageUploader()
        self.patcher = mock.patch('tripleo_common.image.image_uploader.Client')
        self.dockermock = self.patcher.start()

    def tearDown(self):
        super(TestDockerImageUploader, self).tearDown()
        self.patcher.stop()

    def test_upload_image(self):
        image = 'tripleoupstream/heat-docker-agents-centos'
        tag = 'latest'
        pull_source = 'docker.io'
        push_destination = 'localhost:8787'

        self.uploader.upload_image(image + ':' + tag,
                                   pull_source,
                                   push_destination)

        self.dockermock.assert_called_once_with(
            base_url='unix://var/run/docker.sock')

        self.dockermock.return_value.pull.assert_called_once_with(
            pull_source + '/' + image,
            tag=tag, stream=True, insecure_registry=True)
        self.dockermock.return_value.tag.assert_called_once_with(
            image=pull_source + '/' + image + ':' + tag,
            repository=push_destination + '/' + image,
            tag=tag, force=True)
        self.dockermock.return_value.push(
            push_destination + '/' + image,
            tag=tag, stream=True, insecure_registry=True)
