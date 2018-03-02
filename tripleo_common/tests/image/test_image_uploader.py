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

import json
import mock
import operator
import requests
import six
import urllib3

from tripleo_common.image.exception import ImageUploaderException
from tripleo_common.image import image_uploader
from tripleo_common.tests import base
from tripleo_common.tests.image import fakes


filedata = six.u(
    """container_images:
    - imagename: docker.io/tripleomaster/heat-docker-agents-centos:latest
      push_destination: localhost:8787
    - imagename: docker.io/tripleomaster/centos-binary-nova-compute:liberty
      push_destination: localhost:8787
    - imagename: docker.io/tripleomaster/centos-binary-nova-libvirt:liberty
    - imagename: docker.io/tripleomaster/image-with-missing-tag
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
    @mock.patch('tripleo_common.image.image_uploader.'
                'DockerImageUploader.is_insecure_registry',
                return_value=True)
    @mock.patch('tripleo_common.image.image_uploader.'
                'DockerImageUploader._images_match',
                return_value=False)
    @mock.patch('os.path.isfile', return_value=True)
    @mock.patch('fcntl.ioctl', side_effect=Exception)
    @mock.patch('tripleo_common.image.image_uploader.Client')
    def test_file_parsing(self, mockdocker, mockioctl, mockpath,
                          mock_images_match, mock_is_insecure):
        manager = image_uploader.ImageUploadManager(self.filelist, debug=True)
        parsed_data = manager.upload()
        mockpath(self.filelist[0])

        expected_data = fakes.create_parsed_upload_images()
        sorted_expected_data = sorted(expected_data,
                                      key=operator.itemgetter('imagename'))
        sorted_parsed_data = sorted(parsed_data,
                                    key=operator.itemgetter('imagename'))
        self.assertEqual(sorted_expected_data, sorted_parsed_data)

        dockerc = mockdocker.return_value
        dockerc.remove_image.assert_has_calls([
            mock.call('docker.io/tripleomaster'
                      '/centos-binary-nova-compute:liberty'),
            mock.call('docker.io/tripleomaster'
                      '/centos-binary-nova-libvirt:liberty'),
            mock.call('docker.io/tripleomaster'
                      '/heat-docker-agents-centos:latest'),
            mock.call('docker.io/tripleomaster'
                      '/image-with-missing-tag:latest'),

            mock.call('localhost:8787/tripleomaster'
                      '/centos-binary-nova-compute:liberty'),
            mock.call('localhost:8787/tripleomaster'
                      '/centos-binary-nova-libvirt:liberty'),
            mock.call('localhost:8787/tripleomaster'
                      '/heat-docker-agents-centos:latest'),
            mock.call('localhost:8787/tripleomaster/'
                      'image-with-missing-tag:latest'),
        ])


class TestImageUploader(base.TestCase):

    def setUp(self):
        super(TestImageUploader, self).setUp()

    def test_get_uploader_docker(self):
        uploader = image_uploader.ImageUploader.get_uploader('docker')
        assert isinstance(uploader, image_uploader.DockerImageUploader)

    def test_get_builder_unknown(self):
        self.assertRaises(ImageUploaderException,
                          image_uploader.ImageUploader.get_uploader,
                          'unknown')


class TestDockerImageUploader(base.TestCase):

    def setUp(self):
        super(TestDockerImageUploader, self).setUp()
        self.uploader = image_uploader.DockerImageUploader()
        self.patcher = mock.patch('tripleo_common.image.image_uploader.Client')
        self.dockermock = self.patcher.start()

    def tearDown(self):
        super(TestDockerImageUploader, self).tearDown()
        self.patcher.stop()

    @mock.patch('subprocess.Popen')
    def test_upload_image(self, mock_popen):
        result1 = {
            'Digest': 'a'
        }
        result2 = {
            'Digest': 'b'
        }
        mock_process = mock.Mock()
        mock_process.communicate.side_effect = [
            (json.dumps(result1), ''),
            (json.dumps(result2), ''),
        ]

        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        push_destination = 'localhost:8787'
        push_image = 'localhost:8787/tripleomaster/heat-docker-agents-centos'

        self.uploader.upload_image(image + ':' + tag,
                                   None,
                                   push_destination,
                                   set())

        self.dockermock.assert_called_once_with(
            base_url='unix://var/run/docker.sock', version='auto')

        self.dockermock.return_value.pull.assert_called_once_with(
            image, tag=tag, stream=True)
        self.dockermock.return_value.tag.assert_called_once_with(
            image=image + ':' + tag,
            repository=push_image,
            tag=tag, force=True)
        self.dockermock.return_value.push.assert_called_once_with(
            push_image,
            tag=tag, stream=True)

    @mock.patch('subprocess.Popen')
    def test_upload_image_missing_tag(self, mock_popen):
        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        expected_tag = 'latest'
        push_destination = 'localhost:8787'
        push_image = 'localhost:8787/tripleomaster/heat-docker-agents-centos'

        self.uploader.upload_image(image,
                                   None,
                                   push_destination,
                                   set())

        self.dockermock.assert_called_once_with(
            base_url='unix://var/run/docker.sock', version='auto')

        self.dockermock.return_value.pull.assert_called_once_with(
            image, tag=expected_tag, stream=True)
        self.dockermock.return_value.tag.assert_called_once_with(
            image=image + ':' + expected_tag,
            repository=push_image,
            tag=expected_tag, force=True)
        self.dockermock.return_value.push.assert_called_once_with(
            push_image,
            tag=expected_tag, stream=True)

    @mock.patch('subprocess.Popen')
    def test_upload_image_existing(self, mock_popen):
        result = {
            'Digest': 'a'
        }
        mock_process = mock.Mock()
        mock_process.communicate.return_value = (json.dumps(result), '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        push_destination = 'localhost:8787'

        self.uploader.upload_image(image + ':' + tag,
                                   None,
                                   push_destination,
                                   set())

        self.dockermock.assert_called_once_with(
            base_url='unix://var/run/docker.sock', version='auto')

        # both digests are the same, no pull/push
        self.dockermock.return_value.pull.assert_not_called()
        self.dockermock.return_value.tag.assert_not_called()
        self.dockermock.return_value.push.assert_not_called()

    @mock.patch('requests.get')
    def test_is_insecure_registry_known(self, mock_get):
        self.assertFalse(
            self.uploader.is_insecure_registry('docker.io'))

    @mock.patch('requests.get')
    def test_is_insecure_registry_secure(self, mock_get):
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        mock_get.assert_called_once_with('https://192.0.2.0:8787/')

    @mock.patch('requests.get')
    def test_is_insecure_registry_timeout(self, mock_get):
        mock_get.side_effect = requests.exceptions.ReadTimeout('ouch')
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        mock_get.assert_called_once_with('https://192.0.2.0:8787/')

    @mock.patch('requests.get')
    def test_is_insecure_registry_insecure(self, mock_get):
        mock_get.side_effect = requests.exceptions.SSLError('ouch')
        self.assertTrue(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertTrue(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        mock_get.assert_called_once_with('https://192.0.2.0:8787/')

    @mock.patch('subprocess.Popen')
    def test_discover_image_tag(self, mock_popen):
        result = {
            'Labels': {
                'rdo_version': 'a',
                'build_version': '4.0.0'
            },
            'RepoTags': ['a']
        }
        mock_process = mock.Mock()
        mock_process.communicate.return_value = (json.dumps(result), '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        self.assertEqual(
            'a',
            self.uploader.discover_image_tag('docker.io/t/foo', 'rdo_version')
        )

        # no tag_from_label specified
        self.assertRaises(
            ImageUploaderException,
            self.uploader.discover_image_tag,
            'docker.io/t/foo')

        # missing RepoTags entry
        self.assertRaises(
            ImageUploaderException,
            self.uploader.discover_image_tag,
            'docker.io/t/foo',
            'build_version')

        # missing Labels entry
        self.assertRaises(
            ImageUploaderException,
            self.uploader.discover_image_tag,
            'docker.io/t/foo',
            'version')

        # inspect call failed
        mock_process.returncode = 1
        self.assertRaises(
            ImageUploaderException,
            self.uploader.discover_image_tag,
            'docker.io/t/foo',
            'rdo_version')

    @mock.patch('subprocess.Popen')
    def test_discover_tag_from_inspect(self, mock_popen):
        result = {
            'Labels': {
                'rdo_version': 'a',
                'build_version': '4.0.0',
                'release': '1.0.0',
                'version': '20180125'
            },
            'RepoTags': ['a', '1.0.0-20180125']
        }
        mock_process = mock.Mock()
        mock_process.communicate.return_value = (json.dumps(result), '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        sr = image_uploader.SECURE_REGISTRIES
        # simple label -> tag
        self.assertEqual(
            ('docker.io/t/foo', 'a'),
            image_uploader.discover_tag_from_inspect(
                ('docker.io/t/foo', 'rdo_version', sr))
        )

        # templated labels -> tag
        self.assertEqual(
            ('docker.io/t/foo', '1.0.0-20180125'),
            image_uploader.discover_tag_from_inspect(
                ('docker.io/t/foo', '{release}-{version}', sr))
        )

        # simple label -> tag with fallback
        self.assertEqual(
            ('docker.io/t/foo', 'a'),
            image_uploader.discover_tag_from_inspect(
                ('docker.io/t/foo:a', 'bar', sr))
        )

        # templated labels -> tag with fallback
        self.assertEqual(
            ('docker.io/t/foo', 'a'),
            image_uploader.discover_tag_from_inspect(
                ('docker.io/t/foo:a', '{releases}-{versions}', sr))
        )

        # Invalid template
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            ('docker.io/t/foo', '{release}-{version', sr)
        )

        # Missing label in template
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            ('docker.io/t/foo', '{releases}-{version}', sr)
        )

        # no tag_from_label specified
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            ('docker.io/t/foo', None, sr)
        )

        # missing RepoTags entry
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            ('docker.io/t/foo', 'build_version', sr)
        )

        # missing Labels entry
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            ('docker.io/t/foo', 'version', sr)
        )

        # inspect call failed
        mock_process.returncode = 1
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            ('docker.io/t/foo', 'rdo_version', sr)
        )

    @mock.patch('multiprocessing.Pool')
    def test_discover_image_tags(self, mock_pool):
        mock_pool.return_value.map.return_value = (
            ('docker.io/t/foo', 'a'),
            ('docker.io/t/bar', 'b'),
            ('docker.io/t/baz', 'c')
        )
        images = [
            'docker.io/t/foo',
            'docker.io/t/bar',
            'docker.io/t/baz'
        ]
        self.assertEqual(
            {
                'docker.io/t/foo': 'a',
                'docker.io/t/bar': 'b',
                'docker.io/t/baz': 'c'
            },
            self.uploader.discover_image_tags(images, 'rdo_release')
        )
        mock_pool.return_value.map.assert_called_once_with(
            image_uploader.discover_tag_from_inspect,
            [
                ('docker.io/t/foo', 'rdo_release', set()),
                ('docker.io/t/bar', 'rdo_release', set()),
                ('docker.io/t/baz', 'rdo_release', set())
            ])

    @mock.patch('tenacity.wait.wait_random_exponential.__call__')
    def test_pull_retry(self, mock_wait):
        mock_wait.return_value = 0
        image = 'docker.io/tripleomaster/heat-docker-agents-centos'

        dockerc = self.dockermock.return_value
        dockerc.pull.side_effect = [
            urllib3.exceptions.ReadTimeoutError('p', '/foo', 'ouch'),
            urllib3.exceptions.ReadTimeoutError('p', '/foo', 'ouch'),
            ['{"error": "ouch"}'],
            ['{"error": "ouch"}'],
            ['{"status": "done"}']
        ]
        self.uploader._pull(dockerc, image)

        self.assertEqual(dockerc.pull.call_count, 5)
        dockerc.pull.assert_has_calls([
            mock.call(image, tag=None, stream=True)
        ])

    @mock.patch('tenacity.wait.wait_random_exponential.__call__')
    def test_pull_retry_failure(self, mock_wait):
        mock_wait.return_value = 0
        image = 'docker.io/tripleomaster/heat-docker-agents-centos'

        dockerc = self.dockermock.return_value
        dockerc.pull.side_effect = [
            urllib3.exceptions.ReadTimeoutError('p', '/foo', 'ouch'),
            urllib3.exceptions.ReadTimeoutError('p', '/foo', 'ouch'),
            urllib3.exceptions.ReadTimeoutError('p', '/foo', 'ouch'),
            urllib3.exceptions.ReadTimeoutError('p', '/foo', 'ouch'),
            urllib3.exceptions.ReadTimeoutError('p', '/foo', 'ouch'),
        ]
        self.assertRaises(urllib3.exceptions.ReadTimeoutError,
                          self.uploader._pull, dockerc, image)

        self.assertEqual(dockerc.pull.call_count, 5)
        dockerc.pull.assert_has_calls([
            mock.call(image, tag=None, stream=True)
        ])

    @mock.patch('tenacity.wait.wait_random_exponential.__call__')
    def test_push_retry(self, mock_wait):
        mock_wait.return_value = 0
        image = 'docker.io/tripleoupstream/heat-docker-agents-centos'

        dockerc = self.dockermock.return_value
        dockerc.push.side_effect = [
            ['{"error": "ouch"}'],
            ['{"error": "ouch"}'],
            ['{"error": "ouch"}'],
            ['{"error": "ouch"}'],
            ['{"status": "done"}']
        ]
        self.uploader._push(dockerc, image)

        self.assertEqual(dockerc.push.call_count, 5)
        dockerc.push.assert_has_calls([
            mock.call(image, tag=None, stream=True)
        ])

    @mock.patch('tenacity.wait.wait_random_exponential.__call__')
    def test_push_retry_failure(self, mock_wait):
        mock_wait.return_value = 0
        image = 'docker.io/tripleoupstream/heat-docker-agents-centos'

        dockerc = self.dockermock.return_value
        dockerc.push.side_effect = [
            ['{"error": "ouch"}'],
            ['{"error": "ouch"}'],
            ['{"error": "ouch"}'],
            ['{"error": "ouch"}'],
            ['{"error": "ouch"}'],
        ]
        self.assertRaises(ImageUploaderException,
                          self.uploader._push, dockerc, image)

        self.assertEqual(dockerc.push.call_count, 5)
        dockerc.push.assert_has_calls([
            mock.call(image, tag=None, stream=True)
        ])

    @mock.patch('tripleo_common.image.image_uploader.'
                'DockerImageUploader._inspect')
    def test_images_match(self, mock_inspect):
        mock_inspect.side_effect = [{'Digest': 'a'}, {'Digest': 'b'}]
        self.assertFalse(self.uploader._images_match('foo', 'bar', set()))

        mock_inspect.side_effect = [{'Digest': 'a'}, {'Digest': 'a'}]
        self.assertTrue(self.uploader._images_match('foo', 'bar', set()))

        mock_inspect.side_effect = [{}, {'Digest': 'b'}]
        self.assertFalse(self.uploader._images_match('foo', 'bar', set()))

        mock_inspect.side_effect = [{'Digest': 'a'}, {}]
        self.assertFalse(self.uploader._images_match('foo', 'bar', set()))

        mock_inspect.side_effect = [None, None]
        self.assertFalse(self.uploader._images_match('foo', 'bar', set()))

        mock_inspect.side_effect = ImageUploaderException()
        self.assertFalse(self.uploader._images_match('foo', 'bar', set()))
