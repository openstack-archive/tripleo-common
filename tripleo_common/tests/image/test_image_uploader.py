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
import os
import requests
from requests_mock.contrib import fixture as rm_fixture
import six
from six.moves.urllib.parse import urlparse
import tempfile
import urllib3

from oslo_concurrency import processutils
from tripleo_common.image.exception import ImageNotFoundException
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

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    @mock.patch('tripleo_common.image.base.open',
                mock.mock_open(read_data=filedata), create=True)
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.is_insecure_registry',
                return_value=True)
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._images_match',
                return_value=False)
    @mock.patch('os.path.isfile', return_value=True)
    @mock.patch('fcntl.ioctl', side_effect=Exception)
    @mock.patch('tripleo_common.image.image_uploader.Client')
    @mock.patch('tripleo_common.image.image_uploader.'
                'get_undercloud_registry', return_value='192.0.2.0:8787')
    def test_file_parsing(self, mock_gur, mockdocker, mockioctl, mockpath,
                          mock_images_match, mock_is_insecure, mock_inspect,
                          mock_auth):

        mock_inspect.return_value = {}
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
            mock.call('192.0.2.0:8787/tripleomaster'
                      '/centos-binary-nova-libvirt:liberty'),
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
                      '/heat-docker-agents-centos:latest'),
            mock.call('localhost:8787/tripleomaster/'
                      'image-with-missing-tag:latest'),
        ])

    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    def test_get_undercloud_registry(self, mock_interfaces, mock_addresses):
        mock_interfaces.return_value = ['lo', 'eth0']
        self.assertEqual(
            'localhost:8787',
            image_uploader.get_undercloud_registry()
        )

        mock_interfaces.return_value = ['lo', 'eth0', 'br-ctlplane']
        mock_addresses.return_value = {
            2: [{'addr': '192.0.2.0'}]
        }
        self.assertEqual(
            '192.0.2.0:8787',
            image_uploader.get_undercloud_registry()
        )

    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    def test_get_push_destination(self, mock_interfaces, mock_addresses):
        mock_interfaces.return_value = ['lo', 'eth0', 'br-ctlplane']
        mock_addresses.return_value = {
            2: [{'addr': '192.0.2.0'}]
        }
        manager = image_uploader.ImageUploadManager(self.filelist, debug=True)
        self.assertEqual(
            '192.0.2.0:8787',
            manager.get_push_destination({})
        )
        self.assertEqual(
            '192.0.2.1:8787',
            manager.get_push_destination({'push_destination':
                                          '192.0.2.1:8787'})
        )
        self.assertEqual(
            '192.0.2.0:8787',
            manager.get_push_destination({'push_destination': False})
        )
        self.assertEqual(
            '192.0.2.0:8787',
            manager.get_push_destination({'push_destination': True})
        )
        self.assertEqual(
            '192.0.2.0:8787',
            manager.get_push_destination({'push_destination': None})
        )


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


class TestBaseImageUploader(base.TestCase):

    def setUp(self):
        super(TestBaseImageUploader, self).setUp()
        self.uploader = image_uploader.BaseImageUploader()
        self.uploader._inspect.retry.sleep = mock.Mock()
        self.requests = self.useFixture(rm_fixture.Fixture())

    def test_is_insecure_registry_known(self):
        self.assertFalse(
            self.uploader.is_insecure_registry('docker.io'))

    def test_is_insecure_registry_secure(self):
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertEqual(
            'https://192.0.2.0:8787/',
            self.requests.request_history[0].url
        )

    def test_is_insecure_registry_timeout(self):
        self.requests.get(
            'https://192.0.2.0:8787/',
            exc=requests.exceptions.ReadTimeout('ouch'))
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertEqual(
            'https://192.0.2.0:8787/',
            self.requests.request_history[0].url
        )

    def test_is_insecure_registry_insecure(self):
        self.requests.get(
            'https://192.0.2.0:8787/',
            exc=requests.exceptions.SSLError('ouch'))
        self.assertTrue(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertTrue(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertEqual(
            'https://192.0.2.0:8787/',
            self.requests.request_history[0].url
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    def test_discover_image_tag(self, mock_inspect, mock_auth):
        mock_inspect.return_value = {
            'Labels': {
                'rdo_version': 'a',
                'build_version': '4.0.0'
            },
            'RepoTags': ['a']
        }

        self.assertEqual(
            'a',
            self.uploader.discover_image_tag('docker.io/t/foo:b',
                                             'rdo_version')
        )

        # no tag_from_label specified
        self.assertRaises(
            ImageUploaderException,
            self.uploader.discover_image_tag,
            'docker.io/t/foo:b')

        # missing RepoTags entry
        self.assertRaises(
            ImageUploaderException,
            self.uploader.discover_image_tag,
            'docker.io/t/foo:b',
            'build_version')

        # missing Labels entry
        self.assertRaises(
            ImageUploaderException,
            self.uploader.discover_image_tag,
            'docker.io/t/foo:b',
            'version')

        # inspect call failed
        mock_inspect.side_effect = ImageNotFoundException()
        self.assertRaises(
            ImageNotFoundException,
            self.uploader.discover_image_tag,
            'docker.io/t/foo:b',
            'rdo_version')

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    def test_discover_tag_from_inspect(self, mock_inspect, mock_auth):
        mock_inspect.return_value = {
            'Labels': {
                'rdo_version': 'a',
                'build_version': '4.0.0',
                'release': '1.0.0',
                'version': '20180125'
            },
            'RepoTags': ['a', '1.0.0-20180125']
        }

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
        mock_inspect.side_effect = ImageUploaderException()
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            ('docker.io/t/foo', 'rdo_version', sr)
        )

    @mock.patch('concurrent.futures.ThreadPoolExecutor')
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

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
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

    def test_authenticate(self):
        req = self.requests
        auth = image_uploader.BaseImageUploader.authenticate
        url1 = urlparse('docker://docker.io/t/nova-api:latest')

        # no auth required
        req.get('https://registry-1.docker.io/v2/', status_code=200)
        self.assertNotIn('Authorization', auth(url1).headers)

        # missing 'www-authenticate' header
        req.get('https://registry-1.docker.io/v2/', status_code=401)
        self.assertRaises(ImageUploaderException, auth, url1)

        # unknown 'www-authenticate' header
        req.get('https://registry-1.docker.io/v2/', status_code=401,
                headers={'www-authenticate': 'Foo'})
        self.assertRaises(ImageUploaderException, auth, url1)

        # successful auth requests
        headers = {
            'www-authenticate': 'Bearer '
                                'realm="https://auth.docker.io/token",'
                                'service="registry.docker.io"'
        }
        req.get('https://registry-1.docker.io/v2/', status_code=401,
                headers=headers)
        req.get('https://auth.docker.io/token', json={"token": "asdf1234"})
        self.assertEqual(
            'Bearer asdf1234',
            auth(url1).headers['Authorization']
        )

    def test_authenticate_with_no_service(self):
        req = self.requests
        auth = image_uploader.BaseImageUploader.authenticate
        url1 = urlparse('docker://docker.io/t/nova-api:latest')

        headers = {
            'www-authenticate': 'Bearer '
                                'realm="https://auth.docker.io/token",'
        }
        req.get('https://registry-1.docker.io/v2/', status_code=401,
                headers=headers)
        req.get('https://auth.docker.io/token', json={"token": "asdf1234"})
        self.assertEqual(
            'Bearer asdf1234',
            auth(url1).headers['Authorization']
        )

    def test_fix_dockerio_url(self):
        url1 = urlparse('docker://docker.io/t/nova-api:latest')
        url2 = urlparse('docker://registry-1.docker.io/t/nova-api:latest')
        url3 = urlparse('docker://192.0.2.1:8787/t/nova-api:latest')
        fix = image_uploader.BaseImageUploader._fix_dockerio_url
        # fix urls
        self.assertEqual(url2, fix(url1))

        # no change urls
        self.assertEqual(url2, fix(url2))
        self.assertEqual(url3, fix(url3))

    def test_inspect(self):
        req = self.requests
        session = requests.Session()
        session.headers['Authorization'] = 'Bearer asdf1234'
        inspect = image_uploader.BaseImageUploader._inspect

        url1 = urlparse('docker://docker.io/t/nova-api:latest')

        manifest_resp = {
            'config': {
                'mediaType': 'text/html',
                'digest': 'abcdef'
            },
            'layers': [
                {'digest': 'aaa'},
                {'digest': 'bbb'},
                {'digest': 'ccc'},
            ]
        }
        manifest_headers = {'Docker-Content-Digest': 'eeeeee'}
        tags_resp = {'tags': ['one', 'two', 'latest']}
        config_resp = {
            'created': '2018-10-02T11:13:45.567533229Z',
            'docker_version': '1.13.1',
            'config': {
                'Labels': {
                    'build-date': '20181002',
                    'build_id': '1538477701',
                    'kolla_version': '7.0.0'
                }
            },
            'architecture': 'amd64',
            'os': 'linux',
        }

        req.get('https://registry-1.docker.io/v2/t/nova-api/tags/list',
                json=tags_resp)
        req.get('https://registry-1.docker.io/v2/t/nova-api/blobs/abcdef',
                json=config_resp)

        # test 404 response
        req.get('https://registry-1.docker.io/v2/t/nova-api/manifests/latest',
                status_code=404)
        self.assertRaises(ImageNotFoundException, inspect, url1,
                          session=session)

        # test full response
        req.get('https://registry-1.docker.io/v2/t/nova-api/manifests/latest',
                json=manifest_resp, headers=manifest_headers)

        self.assertEqual(
            {
                'Architecture': 'amd64',
                'Created': '2018-10-02T11:13:45.567533229Z',
                'Digest': 'eeeeee',
                'DockerVersion': '1.13.1',
                'Labels': {
                    'build-date': '20181002',
                    'build_id': '1538477701',
                    'kolla_version': '7.0.0'
                },
                'Layers': ['aaa', 'bbb', 'ccc'],
                'Name': 'docker.io/t/nova-api',
                'Os': 'linux',
                'RepoTags': ['one', 'two', 'latest']
            },
            inspect(url1, session=session)
        )


class TestDockerImageUploader(base.TestCase):

    def setUp(self):
        super(TestDockerImageUploader, self).setUp()
        self.uploader = image_uploader.DockerImageUploader()
        self.uploader._push.retry.sleep = mock.Mock()
        self.uploader._pull.retry.sleep = mock.Mock()
        self.uploader._inspect.retry.sleep = mock.Mock()

        self.patcher = mock.patch('tripleo_common.image.image_uploader.Client')
        self.dockermock = self.patcher.start()

    def tearDown(self):
        super(TestDockerImageUploader, self).tearDown()
        self.patcher.stop()

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    def test_upload_image(self, mock_inspect, mock_auth):
        result1 = {
            'Digest': 'a'
        }
        result2 = {
            'Digest': 'b'
        }
        mock_inspect.side_effect = [result1, result2]

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        push_destination = 'localhost:8787'
        push_image = 'localhost:8787/tripleomaster/heat-docker-agents-centos'

        self.assertEqual(
            ['docker.io/tripleomaster/heat-docker-agents-centos:latest',
             'localhost:8787/tripleomaster/heat-docker-agents-centos:latest'],
            self.uploader.upload_image(
                image + ':' + tag,
                None,
                push_destination,
                set(),
                None,
                None,
                None,
                False,
                'full',
                {}
            )
        )

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

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    def test_upload_image_existing(self, mock_inspect, mock_auth):
        mock_inspect.return_value = {
            'Digest': 'a'
        }
        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        push_destination = 'localhost:8787'

        self.assertEqual(
            [],
            self.uploader.upload_image(
                image + ':' + tag,
                None,
                push_destination,
                set(),
                None,
                None,
                None,
                False,
                'full',
                {}
            )
        )

        # both digests are the same, no pull/push
        self.dockermock.assert_not_called()
        self.dockermock.return_value.pull.assert_not_called()
        self.dockermock.return_value.tag.assert_not_called()
        self.dockermock.return_value.push.assert_not_called()

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    @mock.patch('tripleo_common.actions.'
                'ansible.AnsiblePlaybookAction', autospec=True)
    def test_modify_upload_image(self, mock_ansible, mock_inspect, mock_auth):
        mock_inspect.side_effect = ImageNotFoundException()
        mock_ansible.return_value.run.return_value = {}

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        append_tag = 'modify-123'
        push_destination = 'localhost:8787'
        push_image = 'localhost:8787/tripleomaster/heat-docker-agents-centos'
        playbook = [{
            'tasks': [{
                'import_role': {
                    'name': 'add-foo-plugin'
                },
                'name': 'Import role add-foo-plugin',
                'vars': {
                    'target_image': '%s:%s' % (push_image, tag),
                    'modified_append_tag': append_tag,
                    'source_image': '%s:%s' % (image, tag),
                    'foo_version': '1.0.1',
                    'container_build_tool': 'docker'
                }
            }],
            'hosts': 'localhost'
        }]

        # test response for a partial cleanup
        self.assertEqual(
            ['docker.io/tripleomaster/heat-docker-agents-centos:latest'],
            self.uploader.upload_image(
                image + ':' + tag,
                None,
                push_destination,
                set(),
                append_tag,
                'add-foo-plugin',
                {'foo_version': '1.0.1'},
                False,
                'partial',
                {}
            )
        )

        self.dockermock.assert_called_once_with(
            base_url='unix://var/run/docker.sock', version='auto')

        self.dockermock.return_value.pull.assert_called_once_with(
            image, tag=tag, stream=True)
        mock_ansible.assert_called_once_with(
            playbook=playbook,
            work_dir=mock.ANY,
            verbosity=3,
            extra_env_variables=mock.ANY
        )
        self.dockermock.return_value.tag.assert_not_called()
        self.dockermock.return_value.push.assert_called_once_with(
            push_image,
            tag=tag + append_tag,
            stream=True)

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    @mock.patch('tripleo_common.actions.'
                'ansible.AnsiblePlaybookAction', autospec=True)
    def test_modify_image_failed(self, mock_ansible, mock_inspect, mock_auth):
        mock_inspect.side_effect = ImageNotFoundException()

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        append_tag = 'modify-123'
        push_destination = 'localhost:8787'
        error = processutils.ProcessExecutionError(
            '', 'ouch', -1, 'ansible-playbook')
        mock_ansible.return_value.run.side_effect = error

        self.assertRaises(
            ImageUploaderException,
            self.uploader.upload_image,
            image + ':' + tag, None, push_destination, set(), append_tag,
            'add-foo-plugin', {'foo_version': '1.0.1'}, False, 'full',
            {}
        )

        self.dockermock.assert_called_once_with(
            base_url='unix://var/run/docker.sock', version='auto')

        self.dockermock.return_value.pull.assert_called_once_with(
            image, tag=tag, stream=True)
        self.dockermock.return_value.tag.assert_not_called()
        self.dockermock.return_value.push.assert_not_called()

    @mock.patch('subprocess.Popen')
    @mock.patch('tripleo_common.actions.'
                'ansible.AnsiblePlaybookAction', autospec=True)
    def test_modify_upload_image_dry_run(self, mock_ansible, mock_popen):
        mock_process = mock.Mock()
        mock_popen.return_value = mock_process

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        append_tag = 'modify-123'
        push_destination = 'localhost:8787'

        result = self.uploader.upload_image(
            image + ':' + tag,
            None,
            push_destination,
            set(),
            append_tag,
            'add-foo-plugin',
            {'foo_version': '1.0.1'},
            True,
            'full',
            {}
        )

        self.dockermock.assert_not_called()
        mock_ansible.assert_not_called()
        mock_process.communicate.assert_not_called()
        self.assertEqual([], result)

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    @mock.patch('tripleo_common.actions.'
                'ansible.AnsiblePlaybookAction', autospec=True)
    def test_modify_image_existing(self, mock_ansible, mock_inspect,
                                   mock_auth):
        mock_inspect.return_value = {'Digest': 'a'}

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        append_tag = 'modify-123'
        push_destination = 'localhost:8787'

        result = self.uploader.upload_image(
            image + ':' + tag,
            None,
            push_destination,
            set(),
            append_tag,
            'add-foo-plugin',
            {'foo_version': '1.0.1'},
            False,
            'full',
            {}
        )

        self.dockermock.assert_not_called()
        mock_ansible.assert_not_called()

        self.assertEqual([], result)

    def test_pull_retry(self):
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

    def test_pull_retry_failure(self):
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

    def test_push_retry(self):
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

    def test_push_retry_failure(self):
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


class TestSkopeoImageUploader(base.TestCase):

    def setUp(self):
        super(TestSkopeoImageUploader, self).setUp()
        self.uploader = image_uploader.SkopeoImageUploader()
        self.uploader._copy.retry.sleep = mock.Mock()
        self.uploader._inspect.retry.sleep = mock.Mock()

    @mock.patch('os.environ')
    @mock.patch('subprocess.Popen')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    def test_upload_image(self, mock_auth, mock_inspect,
                          mock_popen, mock_environ):
        mock_process = mock.Mock()
        mock_process.communicate.return_value = ('copy complete', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        mock_environ.copy.return_value = {}
        mock_inspect.return_value = {}

        image = 'docker.io/t/nova-api'
        tag = 'latest'
        push_destination = 'localhost:8787'

        self.assertEqual(
            [],
            self.uploader.upload_image(
                image + ':' + tag,
                None,
                push_destination,
                set(),
                None,
                None,
                None,
                False,
                'full',
                {}
            )
        )
        mock_popen.assert_called_once_with([
            'skopeo',
            'copy',
            'docker://docker.io/t/nova-api:latest',
            'docker://localhost:8787/t/nova-api:latest'],
            env={}, stdout=-1
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    @mock.patch('tripleo_common.image.image_uploader.'
                'SkopeoImageUploader._copy')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._image_exists')
    @mock.patch('tripleo_common.actions.'
                'ansible.AnsiblePlaybookAction', autospec=True)
    def test_modify_upload_image(self, mock_ansible, mock_exists, mock_copy,
                                 mock_inspect, mock_auth):
        mock_exists.return_value = False
        mock_inspect.return_value = {}
        with tempfile.NamedTemporaryFile(delete=False) as logfile:
            self.addCleanup(os.remove, logfile.name)
            mock_ansible.return_value.run.return_value = {
                'log_path': logfile.name
            }

        image = 'docker.io/t/nova-api'
        tag = 'latest'
        append_tag = 'modify-123'
        push_destination = 'localhost:8787'
        push_image = 'localhost:8787/t/nova-api'
        playbook = [{
            'tasks': [{
                'import_role': {
                    'name': 'add-foo-plugin'
                },
                'name': 'Import role add-foo-plugin',
                'vars': {
                    'target_image': '%s:%s' % (push_image, tag),
                    'modified_append_tag': append_tag,
                    'source_image': '%s:%s' % (image, tag),
                    'foo_version': '1.0.1',
                    'container_build_tool': 'buildah'
                }
            }],
            'hosts': 'localhost'
        }]

        # test response for a partial cleanup
        self.assertEqual(
            ['docker.io/t/nova-api:latest'],
            self.uploader.upload_image(
                image + ':' + tag,
                None,
                push_destination,
                set(),
                append_tag,
                'add-foo-plugin',
                {'foo_version': '1.0.1'},
                False,
                'partial',
                {}
            )
        )

        insecure = set()
        mock_inspect.assert_has_calls([
            mock.call(urlparse(
                'docker://docker.io/t/nova-api:latest'
            ), insecure=False, session=mock.ANY)
        ])
        mock_copy.assert_has_calls([
            mock.call(
                urlparse('docker://docker.io/t/nova-api:latest'),
                urlparse('containers-storage:docker.io/t/nova-api:latest'),
                insecure
            ),
            mock.call(
                urlparse('containers-storage:localhost:8787/'
                         't/nova-api:latestmodify-123'),
                urlparse('docker://localhost:8787/'
                         't/nova-api:latestmodify-123'),
                insecure
            )
        ])
        mock_ansible.assert_called_once_with(
            playbook=playbook,
            work_dir=mock.ANY,
            verbosity=3,
            extra_env_variables=mock.ANY
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    @mock.patch('tripleo_common.image.image_uploader.'
                'SkopeoImageUploader._copy')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._image_exists')
    @mock.patch('tripleo_common.actions.'
                'ansible.AnsiblePlaybookAction', autospec=True)
    def test_modify_image_failed(self, mock_ansible, mock_exists, mock_copy,
                                 mock_inspect, mock_auth):
        mock_exists.return_value = False
        mock_inspect.return_value = {}

        image = 'docker.io/t/nova-api'
        tag = 'latest'
        append_tag = 'modify-123'
        push_destination = 'localhost:8787'
        error = processutils.ProcessExecutionError(
            '', 'ouch', -1, 'ansible-playbook')
        mock_ansible.return_value.run.side_effect = error

        self.assertRaises(
            ImageUploaderException,
            self.uploader.upload_image,
            image + ':' + tag, None, push_destination, set(), append_tag,
            'add-foo-plugin', {'foo_version': '1.0.1'}, False, 'full',
            {}
        )

        insecure = set()
        mock_copy.assert_called_once_with(
            urlparse('docker://docker.io/t/nova-api:latest'),
            urlparse('containers-storage:docker.io/t/nova-api:latest'),
            insecure
        )

    @mock.patch('subprocess.Popen')
    @mock.patch('tripleo_common.actions.'
                'ansible.AnsiblePlaybookAction', autospec=True)
    def test_modify_upload_image_dry_run(self, mock_ansible, mock_popen):
        mock_process = mock.Mock()
        mock_popen.return_value = mock_process

        image = 'docker.io/t/nova-api'
        tag = 'latest'
        append_tag = 'modify-123'
        push_destination = 'localhost:8787'

        result = self.uploader.upload_image(
            image + ':' + tag,
            None,
            push_destination,
            set(),
            append_tag,
            'add-foo-plugin',
            {'foo_version': '1.0.1'},
            True,
            'full',
            {}
        )

        mock_ansible.assert_not_called()
        mock_process.communicate.assert_not_called()
        self.assertEqual([], result)

    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    @mock.patch('tripleo_common.actions.'
                'ansible.AnsiblePlaybookAction', autospec=True)
    def test_modify_image_existing(self, mock_ansible, mock_inspect,
                                   mock_auth):
        mock_inspect.return_value = {'Digest': 'a'}

        image = 'docker.io/t/nova-api'
        tag = 'latest'
        append_tag = 'modify-123'
        push_destination = 'localhost:8787'

        result = self.uploader.upload_image(
            image + ':' + tag,
            None,
            push_destination,
            set(),
            append_tag,
            'add-foo-plugin',
            {'foo_version': '1.0.1'},
            False,
            'full',
            {}
        )

        mock_ansible.assert_not_called()

        self.assertEqual([], result)

    @mock.patch('os.environ')
    @mock.patch('subprocess.Popen')
    def test_copy_retry(self, mock_popen, mock_environ):
        mock_success = mock.Mock()
        mock_success.communicate.return_value = ('copy complete', '')
        mock_success.returncode = 0

        mock_failure = mock.Mock()
        mock_failure.communicate.return_value = ('', 'ouch')
        mock_failure.returncode = 1
        mock_popen.side_effect = [
            mock_failure,
            mock_failure,
            mock_failure,
            mock_failure,
            mock_success
        ]
        mock_environ.copy.return_value = {}

        source = urlparse('docker://docker.io/t/nova-api')
        target = urlparse('containers_storage:docker.io/t/nova-api')

        self.uploader._copy(source, target, set())

        self.assertEqual(mock_failure.communicate.call_count, 4)
        self.assertEqual(mock_success.communicate.call_count, 1)

    @mock.patch('os.environ')
    @mock.patch('subprocess.Popen')
    def test_copy_retry_failure(self, mock_popen, mock_environ):
        mock_failure = mock.Mock()
        mock_failure.communicate.return_value = ('', 'ouch')
        mock_failure.returncode = 1
        mock_popen.return_value = mock_failure
        mock_environ.copy.return_value = {}

        source = urlparse('docker://docker.io/t/nova-api')
        target = urlparse('containers_storage:docker.io/t/nova-api')

        self.assertRaises(
            ImageUploaderException, self.uploader._copy, source, target, set())

        self.assertEqual(mock_failure.communicate.call_count, 5)
