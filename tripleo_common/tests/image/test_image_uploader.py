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

import hashlib
import io
import json
import operator
import os
import requests
from requests_mock.contrib import fixture as rm_fixture
import six
from six.moves.urllib.parse import urlparse
import tempfile
from unittest import mock
import zlib

from oslo_concurrency import processutils
from tripleo_common.image.exception import ImageNotFoundException
from tripleo_common.image.exception import ImageRateLimitedException
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


class TestRegistrySessionHelper(base.TestCase):
    def setUp(self):
        super(TestRegistrySessionHelper, self).setUp()

    def test_check_status(self):
        session = mock.Mock()
        raise_for_status_mock = mock.Mock()
        request = mock.Mock()
        request.raise_for_status = raise_for_status_mock
        request.status_code = 200

        image_uploader.RegistrySessionHelper.check_status(session, request)
        raise_for_status_mock.assert_called_once()

    def test_check_status_reauth(self):
        session = mock.Mock()
        session_reauth_mock = mock.Mock()
        session.headers = {}
        session.auth_args = {}
        session.reauthenticate = session_reauth_mock
        raise_for_status_mock = mock.Mock()
        request = mock.Mock()
        request.headers = {'www-authenticate': 'foo'}
        request.raise_for_status = raise_for_status_mock
        request.status_code = 401

        image_uploader.RegistrySessionHelper.check_status(session, request)
        session_reauth_mock.assert_called_once_with()
        raise_for_status_mock.assert_called_once()

    def test_check_status_ratelimit(self):
        session = mock.Mock()
        session_reauth_mock = mock.Mock()
        session.headers = {}
        session.auth_args = {}
        session.reauthenticate = session_reauth_mock
        raise_for_status_mock = mock.Mock()
        request = mock.Mock()
        request.headers = {'www-authenticate': 'foo'}
        request.raise_for_status = raise_for_status_mock
        request.status_code = 429

        self.assertRaises(ImageRateLimitedException,
                          image_uploader.RegistrySessionHelper.check_status,
                          session,
                          request)

    def test_check_redirect_trusted_no_redirect(self):
        get_mock = mock.Mock()
        session = mock.Mock()
        session.headers = {'Authorization': 'foo'}
        session.auth_args = {}
        session.get = get_mock
        resp = mock.Mock()
        resp.status_code = 200

        r = image_uploader.RegistrySessionHelper.check_redirect_trusted(
            resp, session)

        self.assertEqual(resp, r)

    def test_check_redirect_trusted_is_trusted(self):
        get_result = mock.Mock()
        get_result.status_code = 200
        get_mock = mock.Mock()
        get_mock.return_value = get_result
        session = mock.Mock()
        session.headers = {'Authorization': 'foo'}
        session.auth_args = {}
        session.get = get_mock
        resp = mock.Mock()
        resp.headers = {'Location': 'https://registry.redhat.io/v2'}
        resp.status_code = 307

        r = image_uploader.RegistrySessionHelper.check_redirect_trusted(
            resp, session)

        self.assertNotEqual(resp, r)
        self.assertEqual(get_result, r)
        get_mock.assert_called_once_with('https://registry.redhat.io/v2',
                                         stream=True,
                                         timeout=30)
        self.assertEqual(session.headers['Authorization'], 'foo')

    def test_check_redirect_trusted_not_trusted(self):
        get_result = mock.Mock()
        get_result.status_code = 200
        get_mock = mock.Mock()
        get_mock.return_value = get_result
        session = mock.Mock()
        session.headers = {'Authorization': 'foo'}
        session.auth_args = {}
        session.get = get_mock
        resp = mock.Mock()
        resp.headers = {'Location': 'http://172.16.12.12:8787/'}
        resp.status_code = 307

        r = image_uploader.RegistrySessionHelper.check_redirect_trusted(
            resp, session, False, 12)

        self.assertNotEqual(resp, r)
        self.assertEqual(get_result, r)
        get_mock.assert_called_once_with('http://172.16.12.12:8787/',
                                         stream=False,
                                         timeout=12)
        self.assertEqual(session.headers['Authorization'], 'foo')

    @mock.patch('tripleo_common.image.image_uploader.RegistrySessionHelper'
                '.check_status')
    def test_action(self, mock_status):
        request_session = mock.Mock()
        mock_get = mock.Mock()
        mock_get.return_value = {}
        request_session.get = mock_get

        image_uploader.RegistrySessionHelper._action('get', request_session)
        mock_get.assert_called_once_with()
        mock_status.assert_called_once_with(session=request_session,
                                            request={})

    @mock.patch('tripleo_common.image.image_uploader.RegistrySessionHelper'
                '.check_status')
    def test_action_reauth(self, mock_status):
        exc_response = mock.Mock()
        exc_response.status_code = 401
        auth_exc = requests.exceptions.HTTPError(response=exc_response)
        mock_status.side_effect = [auth_exc, True]
        request_session = mock.Mock()
        mock_get = mock.Mock()
        mock_get.return_value = {}
        request_session.get = mock_get

        image_uploader.RegistrySessionHelper._action('get', request_session)

        get_call = mock.call()
        get_calls = [get_call, get_call]
        mock_get.assert_has_calls(get_calls)
        status_call = mock.call(session=request_session, request={})
        status_calls = [status_call, status_call]
        mock_status.assert_has_calls(status_calls)

    @mock.patch('tripleo_common.image.image_uploader.RegistrySessionHelper'
                '.check_status')
    def test_action_reauth_fail(self, mock_status):
        exc_response = mock.Mock()
        exc_response.status_code = 404
        auth_exc = requests.exceptions.HTTPError(response=exc_response)
        mock_status.side_effect = auth_exc
        request_session = mock.Mock()
        mock_get = mock.Mock()
        mock_get.return_value = {}
        request_session.get = mock_get

        self.assertRaises(requests.exceptions.HTTPError,
                          image_uploader.RegistrySessionHelper._action,
                          'get',
                          request_session)

        mock_get.assert_called_once_with()
        mock_status.assert_called_once_with(session=request_session,
                                            request={})

    @mock.patch('tripleo_common.image.image_uploader.RegistrySessionHelper'
                '._action')
    def test_get(self, mock_action):
        request_session = mock.Mock()
        image_uploader.RegistrySessionHelper.get(request_session)

        mock_action.assert_called_once_with('get',
                                            request_session)

    @mock.patch('tripleo_common.image.image_uploader.RegistrySessionHelper'
                '._action')
    def test_patch(self, mock_action):
        request_session = mock.Mock()
        image_uploader.RegistrySessionHelper.patch(request_session)

        mock_action.assert_called_once_with('patch',
                                            request_session)

    @mock.patch('tripleo_common.image.image_uploader.RegistrySessionHelper'
                '._action')
    def test_post(self, mock_action):
        request_session = mock.Mock()
        image_uploader.RegistrySessionHelper.post(request_session)

        mock_action.assert_called_once_with('post',
                                            request_session)

    @mock.patch('tripleo_common.image.image_uploader.RegistrySessionHelper'
                '._action')
    def test_put(self, mock_action):
        request_session = mock.Mock()
        image_uploader.RegistrySessionHelper.put(request_session)

        mock_action.assert_called_once_with('put',
                                            request_session)


class TestImageUploadManager(base.TestCase):
    def setUp(self):
        super(TestImageUploadManager, self).setUp()
        files = []
        files.append('testfile')
        self.filelist = files

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._fetch_manifest')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_registry_to_registry')
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
    @mock.patch('tripleo_common.image.image_uploader.'
                'get_undercloud_registry', return_value='192.0.2.0:8787')
    def test_file_parsing(self, mock_gur, mockioctl, mockpath,
                          mock_images_match, mock_is_insecure, mock_inspect,
                          mock_auth, mock_copy, mock_manifest,
                          check_status):

        mock_manifest.return_value = '{"layers": []}'
        mock_inspect.return_value = {}
        manager = image_uploader.ImageUploadManager(self.filelist)
        parsed_data = manager.upload()
        mockpath(self.filelist[0])

        expected_data = fakes.create_parsed_upload_images()
        sorted_expected_data = sorted(expected_data,
                                      key=operator.itemgetter('imagename'))
        sorted_parsed_data = sorted(parsed_data,
                                    key=operator.itemgetter('imagename'))
        self.assertEqual(sorted_expected_data, sorted_parsed_data)

    @mock.patch('subprocess.Popen', autospec=True)
    @mock.patch('socket.gethostname', return_value='uc.somedomain')
    def test_get_undercloud_registry_ipv4(self, mock_gethostname,
                                          mock_popen):
        mock_process = mock.Mock()
        mock_process.communicate.return_value = (
            '192.0.2.1 uc.ctlplane.localdomain uc.ctlplane', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        self.assertEqual('uc.ctlplane.localdomain:8787',
                         image_uploader.get_undercloud_registry())

    @mock.patch('subprocess.Popen', autospec=True)
    @mock.patch('socket.gethostname', return_value='uc.somedomain')
    def test_get_undercloud_registry_ipv6(self, mock_gethostname,
                                          mock_popen):
        mock_process = mock.Mock()
        mock_process.communicate.return_value = (
            'fd12::1 uc.ctlplane.localdomain uc.ctlplane', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        self.assertEqual('uc.ctlplane.localdomain:8787',
                         image_uploader.get_undercloud_registry())

    @mock.patch('subprocess.Popen', autospec=True)
    @mock.patch('socket.gethostname', return_value='localhost.localdomain')
    def test_get_undercloud_registry_no_etc_hosts(self, mock_gethostname,
                                                  mock_popen):
        mock_process = mock.Mock()
        mock_process.communicate.return_value = ('', '')
        mock_process.returncode = 2
        mock_popen.return_value = mock_process
        self.assertEqual('localhost:8787',
                         image_uploader.get_undercloud_registry())

    @mock.patch('subprocess.Popen', autospec=True)
    @mock.patch('socket.gethostname', return_value='undercloud.somedomain')
    def test_get_push_destination(self, mock_gethostname, mock_popen):
        mock_process = mock.Mock()
        mock_process.communicate.return_value = (
            'fd12::1 uc.ctlplane.localdomain uc.ctlplane', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        manager = image_uploader.ImageUploadManager(self.filelist)
        self.assertEqual(
            'uc.ctlplane.localdomain:8787',
            manager.get_push_destination({})
        )
        self.assertEqual(
            '192.0.2.1:8787',
            manager.get_push_destination({'push_destination':
                                          '192.0.2.1:8787'})
        )
        self.assertEqual(
            'uc.ctlplane.localdomain:8787',
            manager.get_push_destination({'push_destination': False})
        )
        self.assertEqual(
            'uc.ctlplane.localdomain:8787',
            manager.get_push_destination({'push_destination': True})
        )
        self.assertEqual(
            'uc.ctlplane.localdomain:8787',
            manager.get_push_destination({'push_destination': None})
        )

    def test_get_uploader_python(self):
        manager = image_uploader.ImageUploadManager(self.filelist)
        uploader = manager.get_uploader('python')
        assert isinstance(uploader, image_uploader.PythonImageUploader)

    def test_get_uploader_skopeo(self):
        manager = image_uploader.ImageUploadManager(self.filelist)
        uploader = manager.get_uploader('skopeo')
        assert isinstance(uploader, image_uploader.SkopeoImageUploader)

    def test_get_builder_unknown(self):
        manager = image_uploader.ImageUploadManager(self.filelist)
        self.assertRaises(ImageUploaderException,
                          manager.get_uploader,
                          'unknown')

    def test_validate_registry_credentials(self):
        # valid credentials
        image_uploader.ImageUploadManager(
            self.filelist,
            registry_credentials=None)
        image_uploader.ImageUploadManager(
            self.filelist,
            registry_credentials={})
        manager = image_uploader.ImageUploadManager(
            self.filelist,
            registry_credentials={
                'docker.io': {'my_username': 'my_password'},
                u'quay.io': {u'quay_username': u'quay_password'},
            })
        self.assertEqual(
            ('my_username', 'my_password'),
            manager.uploader('python').credentials_for_registry('docker.io')
        )
        self.assertEqual(
            ('quay_username', 'quay_password'),
            manager.uploader('python').credentials_for_registry('quay.io')
        )

        # invalid credentials
        self.assertRaises(
            TypeError,
            image_uploader.ImageUploadManager,
            self.filelist,
            registry_credentials='foo'
        )
        self.assertRaises(
            TypeError,
            image_uploader.ImageUploadManager,
            self.filelist,
            registry_credentials={
                1234: {'my_username': 'my_password'},
            }
        )
        self.assertRaises(
            TypeError,
            image_uploader.ImageUploadManager,
            self.filelist,
            registry_credentials={
                'docker.io': {True: 'my_password'},
            }
        )
        self.assertRaises(
            TypeError,
            image_uploader.ImageUploadManager,
            self.filelist,
            registry_credentials={
                'docker.io': {'my_username': True},
            }
        )
        self.assertRaises(
            TypeError,
            image_uploader.ImageUploadManager,
            self.filelist,
            registry_credentials={
                'docker.io': {'my_username': 'my_password', 'foo': 'bar'},
            }
        )


class TestUploadTask(base.TestCase):
    def test_basics(self):
        obj = image_uploader.UploadTask(
            image_name='foo:bar',
            pull_source='docker.io/namespace',
            push_destination='127.0.0.1:8787',
            append_tag='baz',
            modify_role=None,
            modify_vars=None,
            cleanup=False,
            multi_arch=False)
        self.assertEqual(obj.repo, 'docker.io/namespace/foo')
        self.assertEqual(obj.source_tag, 'bar')
        self.assertEqual(obj.target_tag, 'barbaz')
        self.assertEqual(obj.target_image_no_tag,
                         '127.0.0.1:8787/namespace/foo')
        self.assertEqual(obj.target_image,
                         '127.0.0.1:8787/namespace/foo:barbaz')

    def test_repo_pull_source_trailing_slash(self):
        obj = image_uploader.UploadTask(
            image_name='foo:bar',
            pull_source='docker.io/namespace/',
            push_destination='127.0.0.1:8787',
            append_tag=None,
            modify_role=None,
            modify_vars=None,
            cleanup=False,
            multi_arch=False)
        self.assertEqual(obj.repo, 'docker.io/namespace/foo')

    def test_repo_push_destination_trailing_slash(self):
        obj = image_uploader.UploadTask(
            image_name='foo:bar',
            pull_source='docker.io/namespace',
            push_destination='127.0.0.1:8787/',
            append_tag=None,
            modify_role=None,
            modify_vars=None,
            cleanup=False,
            multi_arch=False)
        self.assertEqual(obj.target_image_no_tag,
                         '127.0.0.1:8787/namespace/foo')


class TestBaseImageUploader(base.TestCase):

    def setUp(self):
        super(TestBaseImageUploader, self).setUp()
        self.uploader = image_uploader.BaseImageUploader()
        self.uploader.init_registries_cache()
        # pylint: disable=no-member
        self.uploader._inspect.retry.sleep = mock.Mock()
        self.requests = self.useFixture(rm_fixture.Fixture())

    @mock.patch.object(requests.Session, 'get', return_value=True)
    def test_is_insecure_registry_known(self, mock_session):
        self.assertFalse(
            self.uploader.is_insecure_registry('docker.io'))

    @mock.patch.object(requests.Session, 'get', return_value=True)
    def test_is_insecure_registry_secure(self, mock_session):
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        calls = [mock.call('https://192.0.2.0:8787/v2', timeout=30)]
        mock_session.assert_has_calls(calls)
        self.assertEqual(mock_session.call_count, 1)

    @mock.patch.object(requests.Session, 'get',
                       side_effect=[requests.exceptions.SSLError('err'), True])
    def test_is_insecure_registry_bad_cert(self, mock_session):
        self.assertTrue(
            self.uploader.is_insecure_registry('bcert:8787'))
        self.assertTrue(
            self.uploader.is_insecure_registry('bcert:8787'))
        calls = [mock.call('https://bcert:8787/v2', timeout=30),
                 mock.call('https://bcert:8787/v2', timeout=30, verify=False)]
        mock_session.assert_has_calls(calls)
        self.assertEqual(mock_session.call_count, 2)

    @mock.patch.object(requests.Session, 'get',
                       side_effect=requests.exceptions.ReadTimeout('ouch'))
    def test_is_insecure_registry_timeout(self, mock_session):
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertFalse(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        calls = [mock.call('https://192.0.2.0:8787/v2', timeout=30)]
        mock_session.assert_has_calls(calls)
        self.assertEqual(mock_session.call_count, 1)

    @mock.patch.object(requests.Session, 'get',
                       side_effect=requests.exceptions.SSLError('ouch'))
    def test_is_insecure_registry_insecure(self, mock_session):
        self.assertTrue(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        self.assertTrue(
            self.uploader.is_insecure_registry('192.0.2.0:8787'))
        calls = [mock.call('https://192.0.2.0:8787/v2', timeout=30),
                 mock.call('https://192.0.2.0:8787/v2', timeout=30,
                           verify=False)]
        mock_session.assert_has_calls(calls)
        self.assertEqual(mock_session.call_count, 2)

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

        # handle auth issues
        mock_401 = mock.Mock()
        mock_401.status_code = 401
        mock_401_except = requests.exceptions.HTTPError(response=mock_401)
        mock_404 = mock.Mock()
        mock_404.status_code = 404
        mock_404_except = requests.exceptions.HTTPError(response=mock_404)
        mock_auth.side_effect = [mock_401_except, mock_404_except]
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', 'rdo_version', False)
        )
        self.assertRaises(
            requests.exceptions.HTTPError,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', 'rdo_version', False)
        )

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

        # simple label -> tag
        self.assertEqual(
            ('docker.io/t/foo', 'a'),
            image_uploader.discover_tag_from_inspect(
                (self.uploader, 'docker.io/t/foo', 'rdo_version', False))
        )

        # templated labels -> tag
        self.assertEqual(
            ('docker.io/t/foo', '1.0.0-20180125'),
            image_uploader.discover_tag_from_inspect(
                (self.uploader, 'docker.io/t/foo', '{release}-{version}',
                 False))
        )

        # simple label -> tag with fallback
        self.assertEqual(
            ('docker.io/t/foo', 'a'),
            image_uploader.discover_tag_from_inspect(
                (self.uploader, 'docker.io/t/foo:a', 'bar', False))
        )

        # templated labels -> tag with fallback
        self.assertEqual(
            ('docker.io/t/foo', 'a'),
            image_uploader.discover_tag_from_inspect(
                (self.uploader, 'docker.io/t/foo:a', '{releases}-{versions}',
                 False))
        )

        # Invalid template
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', '{release}-{version', False)
        )

        # Missing label in template
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', '{releases}-{version}', False)
        )

        # no tag_from_label specified
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', None, False)
        )

        # missing RepoTags entry
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', 'build_version', False)
        )

        # missing Labels entry
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', 'version', False)
        )

        # inspect call failed
        mock_inspect.side_effect = ImageUploaderException()
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', 'rdo_version', False)
        )

        # handle auth issues
        mock_401 = mock.Mock()
        mock_401.status_code = 401
        mock_401_except = requests.exceptions.HTTPError(response=mock_401)
        mock_404 = mock.Mock()
        mock_404.status_code = 404
        mock_404_except = requests.exceptions.HTTPError(response=mock_404)
        mock_auth.side_effect = [mock_401_except, mock_404_except]
        self.assertRaises(
            ImageUploaderException,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', 'rdo_version', False)
        )
        self.assertRaises(
            requests.exceptions.HTTPError,
            image_uploader.discover_tag_from_inspect,
            (self.uploader, 'docker.io/t/foo', 'rdo_version', False)
        )

    @mock.patch('concurrent.futures.ThreadPoolExecutor')
    def test_discover_image_tags(self, mock_pool):
        mock_map = mock.Mock()
        mock_map.return_value = (
            ('docker.io/t/foo', 'a'),
            ('docker.io/t/bar', 'b'),
            ('docker.io/t/baz', 'c')
        )
        mock_pool.return_value.__enter__.return_value.map = mock_map
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
        mock_map.assert_called_once_with(
            image_uploader.discover_tag_from_inspect,
            [
                (self.uploader, 'docker.io/t/foo', 'rdo_release', False),
                (self.uploader, 'docker.io/t/bar', 'rdo_release', False),
                (self.uploader, 'docker.io/t/baz', 'rdo_release', False)
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
        auth = self.uploader.authenticate
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

    def test_authenticate_basic_auth(self):
        req = self.requests
        auth = self.uploader.authenticate
        url1 = urlparse('docker://myrepo.com/t/nova-api:latest')

        # successful auth requests
        headers = {
            'www-authenticate': 'Basic realm="Some Realm"'
        }

        def req_match(request):
            resp = requests.Response()
            resp.headers = headers
            resp.status_code = 401
            # if we got sent an user/password, return 200
            if 'Authorization' in request.headers:
                resp.status_code = 200
            return resp

        req.add_matcher(req_match)
        self.assertEqual(
            'Basic Zm9vOmJhcg==',
            auth(url1, username='foo', password='bar').headers['Authorization']
        )

    def test_authenticate_with_no_service(self):
        req = self.requests
        auth = self.uploader.authenticate
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

    def test_build_url(self):
        url1 = urlparse('docker://docker.io/t/nova-api:latest')
        url2 = urlparse('docker://registry-1.docker.io/t/nova-api:latest')
        url3 = urlparse('docker://192.0.2.1:8787/t/nova-api:latest')
        build = image_uploader.BaseImageUploader._build_url
        insecure_reg = image_uploader.BaseImageUploader.insecure_registries
        secure_reg = image_uploader.BaseImageUploader.secure_registries
        no_verify_reg = image_uploader.BaseImageUploader.no_verify_registries
        mirrors = image_uploader.BaseImageUploader.mirrors
        # fix urls
        self.assertEqual(
            'https://registry-1.docker.io/v2/',
            build(url1, '/')
        )

        # no change urls
        insecure_reg.add('registry-1.docker.io')
        secure_reg.add('192.0.2.1:8787')
        self.assertEqual(
            'https://registry-1.docker.io/v2/t/nova-api/manifests/latest',
            build(url2, '/t/nova-api/manifests/latest')
        )
        self.assertEqual(
            'https://192.0.2.1:8787/v2/t/nova-api/tags/list',
            build(url3, '/t/nova-api/tags/list')
        )
        # "no verify" registries are insecure but still use https
        secure_reg.remove('192.0.2.1:8787')
        no_verify_reg.add('192.0.2.1:8787')
        self.assertEqual(
            'https://192.0.2.1:8787/v2/t/nova-api/tags/list',
            build(url3, '/t/nova-api/tags/list')
        )

        # test mirrors
        mirrors['docker.io'] = 'http://192.0.2.2:8081/registry-1.docker/'
        self.assertEqual(
            'http://192.0.2.2:8081/registry-1.docker/v2/'
            't/nova-api/blobs/asdf1234',
            build(url1, '/t/nova-api/blobs/asdf1234')
        )

    def test_inspect_default_tag(self):
        req = self.requests
        session = requests.Session()
        session.headers['Authorization'] = 'Bearer asdf1234'
        inspect = image_uploader.BaseImageUploader._inspect

        url1 = urlparse('docker://docker.io/t/nova-api:latest')

        manifest_resp = {
            'schemaVersion': 2,
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
        manifest_str = json.dumps(manifest_resp, indent=3)
        manifest_headers = {'Docker-Content-Digest': 'eeeeee'}
        tags_resp = {'tags': ['one', 'two']}
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
        req.get('https://registry-1.docker.io/v2/t/nova-api/manifests/two',
                text=manifest_str, headers=manifest_headers)

        # test default_tag=True
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
                'RepoTags': ['one', 'two'],
                'Tag': 'latest'
            },
            inspect(url1, session=session, default_tag=True)
        )

        # test default_tag=False
        req.get('https://registry-1.docker.io/v2/t/nova-api/manifests/latest',
                status_code=404)
        self.assertRaises(ImageNotFoundException, inspect, url1,
                          session=session,
                          default_tag=False)

        # test default_tag=True, but no tags returned
        tags_resp = {'tags': []}
        req.get('https://registry-1.docker.io/v2/t/nova-api/tags/list',
                json=tags_resp)
        self.assertRaises(ImageNotFoundException, inspect, url1,
                          session=session,
                          default_tag=True)

    def test_inspect(self):
        req = self.requests
        session = requests.Session()
        session.headers['Authorization'] = 'Bearer asdf1234'
        inspect = image_uploader.BaseImageUploader._inspect

        url1 = urlparse('docker://docker.io/t/nova-api:latest')

        manifest_resp = {
            'schemaVersion': 2,
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
        manifest_str = json.dumps(manifest_resp, indent=3)
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
                text=manifest_str, headers=manifest_headers)

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
                'RepoTags': ['one', 'two', 'latest'],
                'Tag': 'latest'
            },
            inspect(url1, session=session)
        )

    def test_inspect_v1_manifest(self):
        req = self.requests
        session = requests.Session()
        session.headers['Authorization'] = 'Bearer asdf1234'
        inspect = image_uploader.BaseImageUploader._inspect

        url1 = urlparse('docker://docker.io/t/nova-api:latest')

        config = {
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
        manifest_resp = {
            'schemaVersion': 1,
            'history': [
                {'v1Compatibility': json.dumps(config)}
            ],
            'config': {
                'mediaType': 'text/html',
                'digest': 'abcdef'
            },
            'fsLayers': [
                {'blobSum': 'ccc'},
                {'blobSum': 'bbb'},
                {'blobSum': 'aaa'},
            ]
        }
        manifest_str = json.dumps(manifest_resp, indent=3)
        manifest_headers = {'Docker-Content-Digest': 'eeeeee'}
        tags_resp = {'tags': ['one', 'two', 'latest']}

        req.get('https://registry-1.docker.io/v2/t/nova-api/tags/list',
                json=tags_resp)

        # test 404 response
        req.get('https://registry-1.docker.io/v2/t/nova-api/manifests/latest',
                status_code=404)
        self.assertRaises(ImageNotFoundException, inspect, url1,
                          session=session)

        # test full response
        req.get('https://registry-1.docker.io/v2/t/nova-api/manifests/latest',
                text=manifest_str, headers=manifest_headers)

        self.assertDictEqual(
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
                'RepoTags': ['one', 'two', 'latest'],
                'Tag': 'latest'
            },
            inspect(url1, session=session)
        )

    def test_inspect_no_digest_header(self):
        req = self.requests
        session = requests.Session()
        session.headers['Authorization'] = 'Bearer asdf1234'
        inspect = image_uploader.BaseImageUploader._inspect

        url1 = urlparse('docker://docker.io/t/nova-api:latest')

        manifest_resp = {
            'schemaVersion': 2,
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
        manifest_str = json.dumps(manifest_resp, indent=3)
        manifest_headers = {}
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
                text=manifest_str, headers=manifest_headers)

        calc_digest = hashlib.sha256()
        calc_digest.update(manifest_str.encode('utf-8'))
        digest = 'sha256:%s' % calc_digest.hexdigest()

        self.assertEqual(
            {
                'Architecture': 'amd64',
                'Created': '2018-10-02T11:13:45.567533229Z',
                'Digest': digest,
                'DockerVersion': '1.13.1',
                'Labels': {
                    'build-date': '20181002',
                    'build_id': '1538477701',
                    'kolla_version': '7.0.0'
                },
                'Layers': ['aaa', 'bbb', 'ccc'],
                'Name': 'docker.io/t/nova-api',
                'Os': 'linux',
                'RepoTags': ['one', 'two', 'latest'],
                'Tag': 'latest'
            },
            inspect(url1, session=session)
        )

    @mock.patch('concurrent.futures.ThreadPoolExecutor')
    def test_list(self, mock_pool):
        mock_map = mock.Mock()
        mock_map.return_value = (
            ('localhost:8787/t/foo', ['a']),
            ('localhost:8787/t/bar', ['b']),
            ('localhost:8787/t/baz', ['c', 'd']),
            ('localhost:8787/t/bink', [])
        )
        mock_pool.return_value.__enter__.return_value.map = mock_map
        session = mock.Mock()
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {
            'repositories': ['t/foo', 't/bar', 't/baz', 't/bink']
        }
        session.get.return_value = response
        self.assertEqual(
            [
                'localhost:8787/t/foo:a',
                'localhost:8787/t/bar:b',
                'localhost:8787/t/baz:c',
                'localhost:8787/t/baz:d'
            ],
            self.uploader.list('localhost:8787', session=session)
        )
        mock_map.assert_called_once_with(
            image_uploader.tags_for_image,
            [
                (self.uploader, 'localhost:8787/t/foo', session),
                (self.uploader, 'localhost:8787/t/bar', session),
                (self.uploader, 'localhost:8787/t/baz', session),
                (self.uploader, 'localhost:8787/t/bink', session)
            ])

    def test_list_404(self):
        # setup bits
        session = mock.Mock()
        response = mock.Mock()
        response.status_code = 404
        session.get.return_value = response
        # execute function
        return_val = self.uploader.list('localhost:8787', session=session)
        # check status of things
        self.assertEqual(
            [],
            return_val
        )

    @mock.patch('concurrent.futures.ThreadPoolExecutor')
    def test_list_500(self, mock_pool):
        session = mock.Mock()
        response = mock.Mock()
        response.status_code = 500
        session.get.return_value = response
        mock_pool.return_value.map.return_value = ()
        self.assertRaises(ImageUploaderException,
                          self.uploader.list,
                          'localhost:8787',
                          session=session)

    def test_tags_for_image(self):
        session = mock.Mock()
        r = mock.Mock()
        r.status_code = 200
        r.json.return_value = {'tags': ['a', 'b', 'c']}
        session.get.return_value = r
        self.uploader.insecure_registries.add('localhost:8787')
        url = 'docker://localhost:8787/t/foo'
        image, tags = self.uploader._tags_for_image(url, session=session)
        self.assertEqual(url, image)
        self.assertEqual(['a', 'b', 'c'], tags)

        # test missing tags file
        r.status_code = 404
        image, tags = self.uploader._tags_for_image(url, session=session)
        self.assertEqual([], tags)

    def test_image_tag_from_url(self):
        u = self.uploader
        self.assertEqual(
            ('/t/foo', 'bar'),
            u._image_tag_from_url(urlparse(
                'docker://docker.io/t/foo:bar'))
        )
        self.assertEqual(
            ('/foo', 'bar'),
            u._image_tag_from_url(urlparse(
                'docker://192.168.2.1:5000/foo:bar'))

        )
        self.assertEqual(
            ('/foo', 'bar'),
            u._image_tag_from_url(urlparse(
                'containers-storage:/foo:bar'))
        )


class TestSkopeoImageUploader(base.TestCase):

    def setUp(self):
        super(TestSkopeoImageUploader, self).setUp()
        self.uploader = image_uploader.SkopeoImageUploader()
        # pylint: disable=no-member
        self.uploader._copy.retry.sleep = mock.Mock()
        # pylint: disable=no-member
        self.uploader._inspect.retry.sleep = mock.Mock()

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    @mock.patch('os.environ')
    @mock.patch('subprocess.Popen')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._inspect')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader.authenticate')
    def test_upload_image(self, mock_auth, mock_inspect,
                          mock_popen, mock_environ, check_status):
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
            self.uploader.upload_image(image_uploader.UploadTask(
                image + ':' + tag,
                None,
                push_destination,
                None,
                None,
                None,
                'full',
                False)
            )
        )
        mock_popen.assert_called_once_with([
            'skopeo',
            'copy',
            'docker://docker.io/t/nova-api:latest',
            'docker://localhost:8787/t/nova-api:latest'],
            env={}, stdout=-1, universal_newlines=True
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
            'hosts': 'localhost',
            'gather_facts': 'no'
        }]

        # test response for a partial cleanup
        self.assertEqual(
            ['docker.io/t/nova-api:latest'],
            self.uploader.upload_image(image_uploader.UploadTask(
                image + ':' + tag,
                None,
                push_destination,
                append_tag,
                'add-foo-plugin',
                {'foo_version': '1.0.1'},
                'partial',
                False)
            )
        )

        mock_inspect.assert_has_calls([
            mock.call(urlparse(
                'docker://docker.io/t/nova-api:latest'
            ), session=mock.ANY)
        ])
        mock_copy.assert_has_calls([
            mock.call(
                urlparse('docker://docker.io/t/nova-api:latest'),
                urlparse('containers-storage:docker.io/t/nova-api:latest')
            ),
            mock.call(
                urlparse('containers-storage:localhost:8787/'
                         't/nova-api:latestmodify-123'),
                urlparse('docker://localhost:8787/'
                         't/nova-api:latestmodify-123')
            )
        ])
        mock_ansible.assert_called_once_with(
            playbook=playbook,
            work_dir=mock.ANY,
            verbosity=1,
            extra_env_variables=mock.ANY,
            override_ansible_cfg=(
                "[defaults]\n"
                "stdout_callback=tripleo_dense\n"
                "log_path="
                "/var/log/tripleo-container-image-prepare-ansible.log\n"
            )
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
            self.uploader.upload_image, image_uploader.UploadTask(
                image + ':' + tag, None, push_destination,
                append_tag, 'add-foo-plugin', {'foo_version': '1.0.1'},
                'full', False)
        )

        mock_copy.assert_called_once_with(
            urlparse('docker://docker.io/t/nova-api:latest'),
            urlparse('containers-storage:docker.io/t/nova-api:latest')
        )

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

        result = self.uploader.upload_image(image_uploader.UploadTask(
            image + ':' + tag,
            None,
            push_destination,
            append_tag,
            'add-foo-plugin',
            {'foo_version': '1.0.1'},
            'full',
            False)
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

        self.uploader._copy(source, target)

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
            ImageUploaderException, self.uploader._copy, source, target)

        self.assertEqual(mock_failure.communicate.call_count, 5)


class TestPythonImageUploader(base.TestCase):

    # pylint: disable=no-member
    def setUp(self):
        super(TestPythonImageUploader, self).setUp()
        self.uploader = image_uploader.PythonImageUploader()
        self.uploader.init_registries_cache()
        u = self.uploader
        u._fetch_manifest.retry.sleep = mock.Mock()
        u._upload_url.retry.sleep = mock.Mock()
        u._copy_layer_local_to_registry.retry.sleep = mock.Mock()
        u._copy_layer_registry_to_registry.retry.sleep = mock.Mock()
        u._copy_registry_to_registry.retry.sleep = mock.Mock()
        u._copy_local_to_registry.retry.sleep = mock.Mock()
        self.requests = self.useFixture(rm_fixture.Fixture())

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._fetch_manifest')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._cross_repo_mount')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_registry_to_registry')
    def test_upload_image(
            self, _copy_registry_to_registry, _cross_repo_mount,
            _fetch_manifest, authenticate, check_status):

        target_session = mock.Mock()
        source_session = mock.Mock()
        authenticate.side_effect = [
            target_session,
            source_session
        ]
        manifest = json.dumps({
            'schemaVersion': 2,
            'mediaType': image_uploader.MEDIA_MANIFEST_V2,
            'config': {
                'digest': 'sha256:1234',
            },
            'layers': [
                {'digest': 'sha256:aaa'},
                {'digest': 'sha256:bbb'},
                {'digest': 'sha256:ccc'}
            ],
        })
        _fetch_manifest.return_value = manifest

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        push_destination = 'localhost:8787'
        # push_image = 'localhost:8787/tripleomaster/heat-docker-agents-centos'
        task = image_uploader.UploadTask(
            image_name=image + ':' + tag,
            pull_source=None,
            push_destination=push_destination,
            append_tag=None,
            modify_role=None,
            modify_vars=None,
            cleanup='full',
            multi_arch=False
        )

        self.assertEqual(
            [],
            self.uploader.upload_image(task)
        )
        source_url = urlparse('docker://docker.io/tripleomaster/'
                              'heat-docker-agents-centos:latest')
        target_url = urlparse('docker://localhost:8787/tripleomaster/'
                              'heat-docker-agents-centos:latest')

        authenticate.assert_has_calls([
            mock.call(
                target_url,
                username=None,
                password=None
            ),
            mock.call(
                source_url,
                username=None,
                password=None
            ),
        ])

        _fetch_manifest.assert_called_once_with(
            source_url, session=source_session, multi_arch=False)

        _cross_repo_mount.assert_called_once_with(
            target_url,
            {
                'sha256:aaa': target_url,
                'sha256:bbb': target_url,
                'sha256:ccc': target_url,
            },
            ['sha256:aaa', 'sha256:bbb', 'sha256:ccc'],
            session=target_session)

        _copy_registry_to_registry.assert_called_once_with(
            source_url,
            target_url,
            source_manifests=[manifest],
            source_session=source_session,
            target_session=target_session,
            source_layers=['sha256:aaa', 'sha256:bbb', 'sha256:ccc'],
            multi_arch=False
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._fetch_manifest')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._cross_repo_mount')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_registry_to_registry')
    def test_authenticate_upload_image(
            self, _copy_registry_to_registry, _cross_repo_mount,
            _fetch_manifest, authenticate, check_status):

        self.uploader.registry_credentials = {
            'docker.io': {'my_username': 'my_password'},
            'localhost:8787': {'local_username': 'local_password'},
        }
        target_session = mock.Mock()
        source_session = mock.Mock()
        authenticate.side_effect = [
            target_session,
            source_session
        ]
        manifest = json.dumps({
            'config': {
                'digest': 'sha256:1234',
            },
            'layers': [
                {'digest': 'sha256:aaa'},
                {'digest': 'sha256:bbb'},
                {'digest': 'sha256:ccc'}
            ],
        })
        _fetch_manifest.return_value = manifest

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        push_destination = 'localhost:8787'
        # push_image = 'localhost:8787/tripleomaster/heat-docker-agents-centos'
        task = image_uploader.UploadTask(
            image_name=image + ':' + tag,
            pull_source=None,
            push_destination=push_destination,
            append_tag=None,
            modify_role=None,
            modify_vars=None,
            cleanup='full',
            multi_arch=False
        )

        self.assertEqual(
            [],
            self.uploader.upload_image(task)
        )
        source_url = urlparse('docker://docker.io/tripleomaster/'
                              'heat-docker-agents-centos:latest')
        target_url = urlparse('docker://localhost:8787/tripleomaster/'
                              'heat-docker-agents-centos:latest')

        authenticate.assert_has_calls([
            mock.call(
                target_url,
                username='local_username',
                password='local_password'
            ),
            mock.call(
                source_url,
                username='my_username',
                password='my_password'
            ),
        ])

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._fetch_manifest')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._cross_repo_mount')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_registry_to_registry')
    def test_insecure_registry(
            self, _copy_registry_to_registry, _cross_repo_mount,
            _fetch_manifest, authenticate, check_status):
        target_session = mock.Mock()
        source_session = mock.Mock()
        authenticate.side_effect = [
            target_session,
            source_session
        ]
        manifest = json.dumps({
            'config': {
                'digest': 'sha256:1234',
            },
            'layers': [
                {'digest': 'sha256:aaa'},
                {'digest': 'sha256:bbb'},
                {'digest': 'sha256:ccc'}
            ],
        })
        _fetch_manifest.return_value = manifest

        image = '192.0.2.0:8787/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        push_destination = 'localhost:8787'
        # push_image = 'localhost:8787/tripleomaster/heat-docker-agents-centos'
        task = image_uploader.UploadTask(
            image_name=image + ':' + tag,
            pull_source=None,
            push_destination=push_destination,
            append_tag=None,
            modify_role=None,
            modify_vars=None,
            cleanup='full',
            multi_arch=False
        )

        self.assertEqual(
            [],
            self.uploader.upload_image(task)
        )
        source_url = urlparse('docker://192.0.2.0:8787/tripleomaster/'
                              'heat-docker-agents-centos:latest')
        target_url = urlparse('docker://localhost:8787/tripleomaster/'
                              'heat-docker-agents-centos:latest')

        authenticate.assert_has_calls([
            mock.call(
                target_url,
                username=None,
                password=None
            ),
            mock.call(
                source_url,
                username=None,
                password=None
            ),
        ])

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._fetch_manifest')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._cross_repo_mount')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_registry_to_registry')
    def test_upload_image_v1_manifest(
            self, _copy_registry_to_registry, _cross_repo_mount,
            _fetch_manifest, authenticate, check_status):

        target_session = mock.Mock()
        source_session = mock.Mock()
        authenticate.side_effect = [
            target_session,
            source_session
        ]
        manifest = json.dumps({
            'schemaVersion': 1,
            'fsLayers': [
                {'blobSum': 'sha256:ccc'},
                {'blobSum': 'sha256:bbb'},
                {'blobSum': 'sha256:aaa'}
            ],
        })
        _fetch_manifest.return_value = manifest

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        push_destination = 'localhost:8787'
        # push_image = 'localhost:8787/tripleomaster/heat-docker-agents-centos'
        task = image_uploader.UploadTask(
            image_name=image + ':' + tag,
            pull_source=None,
            push_destination=push_destination,
            append_tag=None,
            modify_role=None,
            modify_vars=None,
            cleanup='full',
            multi_arch=False
        )

        self.assertEqual(
            [],
            self.uploader.upload_image(task)
        )
        source_url = urlparse('docker://docker.io/tripleomaster/'
                              'heat-docker-agents-centos:latest')
        target_url = urlparse('docker://localhost:8787/tripleomaster/'
                              'heat-docker-agents-centos:latest')

        authenticate.assert_has_calls([
            mock.call(
                target_url,
                username=None,
                password=None
            ),
            mock.call(
                source_url,
                username=None,
                password=None
            ),
        ])

        _fetch_manifest.assert_called_once_with(
            source_url, session=source_session, multi_arch=False)

        _cross_repo_mount.assert_called_once_with(
            target_url,
            {
                'sha256:aaa': target_url,
                'sha256:bbb': target_url,
                'sha256:ccc': target_url,
            },
            ['sha256:aaa', 'sha256:bbb', 'sha256:ccc'],
            session=target_session)

        _copy_registry_to_registry.assert_called_once_with(
            source_url,
            target_url,
            source_manifests=[manifest],
            source_session=source_session,
            target_session=target_session,
            source_layers=['sha256:aaa', 'sha256:bbb', 'sha256:ccc'],
            multi_arch=False
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader.authenticate')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._image_exists')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._fetch_manifest')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._cross_repo_mount')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_registry_to_registry')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_registry_to_local')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader.run_modify_playbook')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_local_to_registry')
    def test_upload_image_modify(
            self, _copy_local_to_registry, run_modify_playbook,
            _copy_registry_to_local, _copy_registry_to_registry,
            _cross_repo_mount, _fetch_manifest, _image_exists, authenticate,
            check_status):

        _image_exists.return_value = False
        target_session = mock.Mock()
        source_session = mock.Mock()
        authenticate.side_effect = [
            target_session,
            source_session
        ]
        manifest = json.dumps({
            'schemaVersion': 2,
            'mediaType': image_uploader.MEDIA_MANIFEST_V2,
            'config': {
                'digest': 'sha256:1234',
            },
            'layers': [
                {'digest': 'sha256:aaa'},
                {'digest': 'sha256:bbb'},
                {'digest': 'sha256:ccc'}
            ],
        })
        _fetch_manifest.return_value = manifest

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        append_tag = 'modify-123'
        push_destination = 'localhost:8787'
        # push_image = 'localhost:8787/tripleomaster/heat-docker-agents-centos'
        task = image_uploader.UploadTask(
            image_name=image + ':' + tag,
            pull_source=None,
            push_destination=push_destination,
            append_tag=append_tag,
            modify_role='add-foo-plugin',
            modify_vars={'foo_version': '1.0.1'},
            cleanup='full',
            multi_arch=False
        )

        source_url = urlparse(
            'docker://docker.io/tripleomaster/'
            'heat-docker-agents-centos:latest')
        unmodified_target_url = urlparse(
            'docker://localhost:8787/tripleomaster/'
            'heat-docker-agents-centos:latest')
        local_modified_url = urlparse(
            'containers-storage:localhost:8787/tripleomaster/'
            'heat-docker-agents-centos:latestmodify-123')
        target_url = urlparse(
            'docker://localhost:8787/tripleomaster/'
            'heat-docker-agents-centos:latestmodify-123')

        self.assertEqual([
            'localhost:8787/tripleomaster/'
            'heat-docker-agents-centos:latest',
            'localhost:8787/tripleomaster/'
            'heat-docker-agents-centos:latestmodify-123'],
            self.uploader.upload_image(task)
        )
        authenticate.assert_has_calls([
            mock.call(
                target_url,
                username=None,
                password=None
            ),
            mock.call(
                source_url,
                username=None,
                password=None
            ),
        ])

        _fetch_manifest.assert_called_once_with(
            source_url, session=source_session, multi_arch=False)

        _cross_repo_mount.assert_has_calls([
            mock.call(
                unmodified_target_url,
                {
                    'sha256:aaa': target_url,
                    'sha256:bbb': target_url,
                    'sha256:ccc': target_url,
                },
                ['sha256:aaa', 'sha256:bbb', 'sha256:ccc'],
                session=target_session
            ),
            mock.call(
                target_url,
                {
                    'sha256:aaa': target_url,
                    'sha256:bbb': target_url,
                    'sha256:ccc': target_url,
                },
                ['sha256:aaa', 'sha256:bbb', 'sha256:ccc'],
                session=target_session
            )
        ])

        _copy_registry_to_registry.assert_called_once_with(
            source_url,
            unmodified_target_url,
            source_manifests=[manifest],
            source_session=source_session,
            target_session=target_session,
            source_layers=['sha256:aaa', 'sha256:bbb', 'sha256:ccc'],
            multi_arch=False
        )
        _copy_registry_to_local.assert_called_once_with(unmodified_target_url)
        run_modify_playbook.assert_called_once_with(
            'add-foo-plugin',
            {'foo_version': '1.0.1'},
            'localhost:8787/tripleomaster/'
            'heat-docker-agents-centos:latest',
            'localhost:8787/tripleomaster/'
            'heat-docker-agents-centos:latest',
            'modify-123',
            container_build_tool='buildah'
        )
        _copy_local_to_registry.assert_called_once_with(
            local_modified_url,
            target_url,
            session=target_session
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._detect_target_export')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader.credentials_for_registry')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_local_to_registry')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader.authenticate')
    def test_upload_image_local(self, authenticate, mock_copy, mock_creds,
                                mock_detect):

        mock_creds.return_value = (None, None)
        target_session = mock.Mock()
        authenticate.side_effect = [
            target_session
        ]

        image = 'docker.io/tripleomaster/heat-docker-agents-centos'
        tag = 'latest'
        push_destination = 'localhost:8787'
        source_image = 'containers-storage:%s:%s' % (image, tag)
        task = image_uploader.UploadTask(
            image_name=source_image,
            pull_source=None,
            push_destination=push_destination,
            append_tag=None,
            modify_role=None,
            modify_vars=None,
            cleanup='full',
            multi_arch=False
        )

        self.assertEqual(
            [],
            self.uploader.upload_image(task)
        )
        source_url = urlparse(source_image)
        target_url = urlparse('docker://localhost:8787/tripleomaster/'
                              'heat-docker-agents-centos:latest')
        authenticate.assert_has_calls([
            mock.call(
                target_url,
                username=None,
                password=None
            )
        ])
        mock_detect.assert_called_once_with(target_url, target_session)
        mock_copy.assert_called_once_with(source_url, target_url,
                                          session=target_session)

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    def test_fetch_manifest(self, check_status):
        url = urlparse('docker://docker.io/t/nova-api:tripleo-current')
        manifest = '{"layers": []}'
        session = mock.Mock()
        session.get.return_value.text = manifest
        self.assertEqual(
            manifest,
            self.uploader._fetch_manifest(url, session, multi_arch=False)
        )

        session.get.assert_called_once_with(
            'https://registry-1.docker.io/v2/t/'
            'nova-api/manifests/tripleo-current',
            timeout=30,
            headers={
                'Accept': 'application/vnd.docker.distribution'
                          '.manifest.v2+json'
            }
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    def test_upload_url(self, check_status):
        # test with previous request
        previous_request = mock.Mock()
        previous_request.headers = {
            'Location': 'http://192.168.2.1/v2/upload?foo=bar'
        }
        url = urlparse('docker://192.168.2.1/t/nova-api:latest')
        session = mock.Mock()
        self.assertEqual(
            'http://192.168.2.1/v2/upload?foo=bar',
            self.uploader._upload_url(
                url,
                session=session,
                previous_request=previous_request
            )
        )
        session.post.assert_not_called()

        # test with requesting an upload url
        session.post.return_value.headers = {
            'Location': 'http://192.168.2.1/v2/upload?foo=baz'
        }
        self.assertEqual(
            'http://192.168.2.1/v2/upload?foo=baz',
            self.uploader._upload_url(
                url,
                session=session,
                previous_request=None
            )
        )
        session.post.assert_called_once_with(
            'https://192.168.2.1/v2/t/nova-api/blobs/uploads/',
            timeout=30
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._upload_url')
    @mock.patch('tripleo_common.utils.image.uploaded_layers_details')
    def test_copy_layer_registry_to_registry(self, global_check, _upload_url):
        _upload_url.return_value = 'https://192.168.2.1:5000/v2/upload'
        source_url = urlparse('docker://docker.io/t/nova-api:latest')
        target_url = urlparse('docker://192.168.2.1:5000/t/nova-api:latest')
        source_session = requests.Session()
        target_session = requests.Session()

        blob_data = six.b('The Blob')
        calc_digest = hashlib.sha256()
        calc_digest.update(blob_data)
        blob_digest = 'sha256:' + calc_digest.hexdigest()
        layer_entry = {
            'digest': blob_digest,
            'size': 8,
            'mediaType': 'application/vnd.docker.image.rootfs.diff.tar.gzip'
        }
        layer = layer_entry['digest']

        # layer already exists at destination
        global_check.return_value = (None, None)
        self.requests.head(
            'https://192.168.2.1:5000/v2/t/nova-api/blobs/%s' % blob_digest,
            status_code=200
        )
        self.assertIsNone(
            self.uploader._copy_layer_registry_to_registry(
                source_url,
                target_url,
                layer,
                source_session=source_session,
                target_session=target_session
            )
        )

        # layer needs transferring
        self.requests.head(
            'https://192.168.2.1:5000/v2/t/nova-api/blobs/%s' % blob_digest,
            status_code=404
        )
        self.requests.put(
            'https://192.168.2.1:5000/v2/upload',
        )
        self.requests.patch(
            'https://192.168.2.1:5000/v2/upload',
        )
        self.requests.get(
            'https://registry-1.docker.io/v2/t/nova-api/blobs/%s' %
            blob_digest,
            content=blob_data
        )

        self.assertEqual(
            blob_digest,
            self.uploader._copy_layer_registry_to_registry(
                source_url,
                target_url,
                layer,
                source_session=source_session,
                target_session=target_session
            )
        )
        self.assertEqual(
            {
                'digest': blob_digest,
                'mediaType': 'application/'
                             'vnd.docker.image.rootfs.diff.tar.gzip',
                'size': 8
            },
            layer_entry
        )

    def test_assert_scheme(self):
        self.uploader._assert_scheme(
            urlparse('docker://docker.io/foo/bar:latest'),
            'docker'
        )
        self.uploader._assert_scheme(
            urlparse('containers-storage:foo/bar:latest'),
            'containers-storage'
        )
        self.assertRaises(
            ImageUploaderException,
            self.uploader._assert_scheme,
            urlparse('containers-storage:foo/bar:latest'),
            'docker'
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_redirect_trusted')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_manifest_config_to_registry')
    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.get')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._upload_url')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader.'
                '_copy_layer_registry_to_registry')
    def test_copy_registry_to_registry(self, _copy_layer, _upload_url,
                                       mock_get, mock_copy_manifest,
                                       mock_trusted):
        source_url = urlparse('docker://docker.io/t/nova-api:latest')
        target_url = urlparse('docker://192.168.2.1:5000/t/nova-api:latest')
        _upload_url.return_value = 'https://192.168.2.1:5000/v2/upload'

        source_session = mock.Mock()
        target_session = mock.Mock()

        mock_resp = mock.Mock()
        mock_resp.text = '{}'
        mock_get.return_value = mock_resp
        mock_trusted.return_value = mock_resp

        manifest = json.dumps({
            'mediaType': image_uploader.MEDIA_MANIFEST_V2,
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': image_uploader.MEDIA_CONFIG
            },
            'layers': [
                {'digest': 'sha256:aaaa'},
                {'digest': 'sha256:bbbb'},
            ]
        })
        _copy_layer.side_effect = [
            'sha256:aaaa',
            'sha256:bbbb'
        ]

        self.uploader._copy_registry_to_registry(
            source_url, target_url, [manifest],
            source_session=source_session,
            target_session=target_session
        )

        mock_get.assert_called_once_with(
            source_session,
            'https://registry-1.docker.io/v2/t/nova-api/blobs/sha256:1234',
            timeout=30,
            allow_redirects=False
        )
        target_manifest = {
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': 'application/vnd.docker.container.image.v1+json'
            },
            'layers': [
                {'digest': 'sha256:aaaa'},
                {'digest': 'sha256:bbbb'},
            ],
            'mediaType': 'application/vnd.docker.'
                         'distribution.manifest.v2+json',
        }

        mock_trusted.assert_called_once_with(mock_resp,
                                             source_session,
                                             stream=False)
        mock_copy_manifest.assert_has_calls([
            mock.call(
                target_url=target_url,
                manifest_str=mock.ANY,
                config_str='{}',
                target_session=target_session,
                multi_arch=False
            )
        ])
        put_manifest = json.loads(
            mock_copy_manifest.call_args[1]['manifest_str']
        )
        self.assertEqual(target_manifest, put_manifest)

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.check_status')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._build_url')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._image_tag_from_url')
    def test_copy_manifest_config_to_registry(self, image_tag_mock,
                                              build_url_mock, status_mock):

        target_url = urlparse('docker://192.168.2.1:5000/t/nova-api:latest')

        image_tag_mock.return_value = ('t/nova-api', 'latest')

        build_url = 'https://192.168.2.1:5000/v2/t/nova-api'
        build_url_mock.return_value = build_url
        target_session = mock.Mock()
        target_put = mock.Mock()
        target_put.return_value.text = '{}'
        target_session.put = target_put

        config_str = None

        manifest_str = json.dumps({
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': image_uploader.MEDIA_CONFIG
            },
            'layers': [
                {'digest': 'sha256:aaaa'},
                {'digest': 'sha256:bbbb'},
            ],
            'mediaType': image_uploader.MEDIA_MANIFEST_V2
        })
        expected_manifest = {
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': image_uploader.MEDIA_CONFIG
            },
            'layers': [
                {'digest': 'sha256:aaaa'},
                {'digest': 'sha256:bbbb'},
            ],
            'mediaType': image_uploader.MEDIA_MANIFEST_V2
        }

        expected_headers = {
            'Content-Type': image_uploader.MEDIA_MANIFEST_V2
        }
        self.uploader._copy_manifest_config_to_registry(
            target_url, manifest_str, config_str,
            target_session=target_session
        )

        calls = [mock.call(build_url,
                           data=mock.ANY,
                           headers=expected_headers,
                           timeout=30)]
        target_put.assert_has_calls(calls)
        # We're seeing ordering issues with the py27 checking this field
        # so switch to checking it this way
        call_manifest = json.loads(
            target_put.call_args[1]['data'].decode('utf-8')
        )
        self.assertEqual(expected_manifest, call_manifest)

    @mock.patch('tripleo_common.image.image_export.export_manifest_config')
    def test_copy_manifest_config_to_registry_export(self, export_mock):

        target_url = urlparse('docker://192.168.2.1:5000/t/nova-api:latest')
        self.uploader.export_registries.add('192.168.2.1:5000')
        target_session = mock.Mock()
        config_str = None

        manifest_str = json.dumps({
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': image_uploader.MEDIA_CONFIG
            },
            'layers': [
                {'digest': 'sha256:aaaa'},
                {'digest': 'sha256:bbbb'},
            ],
        })
        expected_manifest = {
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': image_uploader.MEDIA_CONFIG
            },
            'layers': [
                {'digest': 'sha256:aaaa'},
                {'digest': 'sha256:bbbb'},
            ],
            'mediaType': image_uploader.MEDIA_MANIFEST_V2
        }

        self.uploader._copy_manifest_config_to_registry(
            target_url, manifest_str, config_str,
            target_session=target_session
        )

        calls = [mock.call(target_url,
                           mock.ANY,
                           image_uploader.MEDIA_MANIFEST_V2,
                           config_str,
                           multi_arch=False)]
        export_mock.assert_has_calls(calls)
        # We're seeing ordering issues with the py27 checking this field
        # so switch to checking it this way
        call_manifest = json.loads(
            export_mock.call_args[0][1]
        )
        self.assertEqual(expected_manifest, call_manifest)

    @mock.patch('tripleo_common.image.image_uploader.'
                'RegistrySessionHelper.put')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._build_url')
    @mock.patch('tripleo_common.image.image_uploader.'
                'BaseImageUploader._image_tag_from_url')
    def test_copy_manifest_config_to_registry_oci(self, image_tag_mock,
                                                  build_url_mock, put_mock):

        target_url = urlparse('docker://192.168.2.1:5000/t/nova-api:latest')

        image_tag_mock.return_value = ('t/nova-api', 'latest')

        build_url = 'https://192.168.2.1:5000/v2/t/nova-api'
        build_url_mock.return_value = build_url
        target_session = mock.Mock()
        put_mock.return_value.text = '{}'

        config_str = None

        manifest_str = json.dumps({
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': image_uploader.MEDIA_CONFIG
            },
            'layers': [
                {'digest': 'sha256:aaaa'},
                {'digest': 'sha256:bbbb'},
            ],
            'mediaType': image_uploader.MEDIA_OCI_MANIFEST_V1
        })
        expected_manifest = {
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': image_uploader.MEDIA_CONFIG
            },
            'layers': [
                {'digest': 'sha256:aaaa'},
                {'digest': 'sha256:bbbb'},
            ],
            'mediaType': image_uploader.MEDIA_MANIFEST_V2
        }

        expected_headers = {
            'Content-Type': image_uploader.MEDIA_MANIFEST_V2
        }
        self.uploader._copy_manifest_config_to_registry(
            target_url, manifest_str, config_str,
            target_session=target_session
        )

        calls = [mock.call(target_session,
                           build_url,
                           data=mock.ANY,
                           headers=expected_headers,
                           timeout=30)]
        put_mock.assert_has_calls(calls)
        # We're seeing ordering issues with the py27 checking this field
        # so switch to checking it this way
        call_manifest = json.loads(
            put_mock.call_args[1]['data'].decode('utf-8')
        )
        self.assertEqual(expected_manifest, call_manifest)

    @mock.patch('os.environ')
    @mock.patch('subprocess.Popen')
    def test_copy_registry_to_local(self, mock_popen, mock_environ):
        mock_success = mock.Mock()
        mock_success.communicate.return_value = (
            six.b('pull complete'),
            six.b('')
        )
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

        self.uploader._copy_registry_to_local(source)

        self.assertEqual(mock_failure.communicate.call_count, 4)
        self.assertEqual(mock_success.communicate.call_count, 1)

    @mock.patch('os.path.exists')
    @mock.patch('subprocess.Popen')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._upload_url')
    @mock.patch('tripleo_common.utils.image.uploaded_layers_details')
    def test_copy_layer_local_to_registry(self, global_check, _upload_url,
                                          mock_popen, mock_exists):
        mock_exists.return_value = True
        _upload_url.return_value = 'https://192.168.2.1:5000/v2/upload'
        target_url = urlparse('docker://192.168.2.1:5000/t/nova-api:latest')
        layer = {'digest': 'sha256:aaaa'}
        target_session = requests.Session()

        blob_data = six.b('The Blob')
        calc_digest = hashlib.sha256()
        calc_digest.update(blob_data)
        blob_digest = 'sha256:' + calc_digest.hexdigest()

        blob_compressed = zlib.compress(blob_data)
        calc_digest = hashlib.sha256()
        calc_digest.update(blob_compressed)
        compressed_digest = 'sha256:' + calc_digest.hexdigest()
        layer_entry = {
            'compressed-diff-digest': compressed_digest,
            'compressed-size': len(compressed_digest),
            'diff-digest': blob_digest,
            'diff-size': len(blob_data),
            'id': 'aaaa'
        }

        # layer already exists at destination
        global_check.return_value = (None, None)
        self.requests.head(
            'https://192.168.2.1:5000/v2/t/'
            'nova-api/blobs/%s' % compressed_digest,
            status_code=404
        )
        self.requests.head(
            'https://192.168.2.1:5000/v2/t/nova-api/blobs/%s' % blob_digest,
            status_code=200
        )
        self.assertIsNone(
            self.uploader._copy_layer_local_to_registry(
                target_url,
                session=target_session,
                layer=layer,
                layer_entry=layer_entry
            )
        )

        # layer needs uploading
        mock_success = mock.Mock()
        mock_success.stdout = io.BytesIO(blob_compressed)
        mock_success.returncode = 0
        mock_popen.return_value = mock_success

        target_session = requests.Session()
        self.requests.head(
            'https://192.168.2.1:5000/v2/t/'
            'nova-api/blobs/%s' % compressed_digest,
            status_code=404
        )
        self.requests.head(
            'https://192.168.2.1:5000/v2/t/nova-api/blobs/%s' % blob_digest,
            status_code=404
        )
        self.requests.patch(
            'https://192.168.2.1:5000/v2/upload',
            status_code=200
        )
        self.requests.put(
            'https://192.168.2.1:5000/v2/upload?digest=%s' % compressed_digest,
            status_code=200
        )
        self.assertEqual(
            compressed_digest,
            self.uploader._copy_layer_local_to_registry(
                target_url,
                session=target_session,
                layer=layer,
                layer_entry=layer_entry
            )
        )
        # test tar-split assemble call
        mock_popen.assert_called_once_with([
            'tar-split', 'asm',
            '--input',
            '/var/lib/containers/storage/overlay-layers/aaaa.tar-split.gz',
            '--path',
            '/var/lib/containers/storage/overlay/aaaa/diff',
            '--compress'
        ], stdout=-1)

        # test side-effect of layer being fully populated
        self.assertEqual({
            'digest': compressed_digest,
            'mediaType': 'application/vnd.docker.image.rootfs.diff.tar.gzip',
            'size': len(blob_compressed)},
            layer
        )

    @mock.patch('tripleo_common.utils.image.uploaded_layers_details')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._image_manifest_config')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._copy_layer_local_to_registry')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._containers_json')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._upload_url')
    def test_copy_local_to_registry(self, _upload_url, _containers_json,
                                    _copy_layer_local_to_registry,
                                    _image_manifest_config, _global_check):
        source_url = urlparse('containers-storage:/t/nova-api:latest')
        target_url = urlparse('docker://192.168.2.1:5000/t/nova-api:latest')
        target_session = requests.Session()
        _upload_url.return_value = 'https://192.168.2.1:5000/v2/upload'
        _global_check.return_value = (None, None)
        layers = [{
            "compressed-diff-digest": "sha256:aeb786",
            "compressed-size": 74703002,
            "compression": 2,
            "created": "2018-11-07T02:45:16.760488331Z",
            "diff-digest": "sha256:f972d1",
            "diff-size": 208811520,
            "id": "f972d1"
        }, {
            "compressed-diff-digest": "sha256:4dc536",
            "compressed-size": 23400,
            "compression": 2,
            "created": "2018-11-07T02:45:21.59385649Z",
            "diff-digest": "sha256:26deb2",
            "diff-size": 18775552,
            "id": "97397b",
            "parent": "f972d1"
        }]
        _containers_json.return_value = layers

        config_str = '{"config": {}}'
        config_digest = 'sha256:1234'

        manifest = {
            'config': {
                'digest': config_digest,
                'size': 2,
                'mediaType': 'application/vnd.docker.container.image.v1+json'
            },
            'layers': [
                {'digest': 'sha256:aeb786'},
                {'digest': 'sha256:4dc536'},
            ],
            'mediaType': 'application/vnd.docker.'
                         'distribution.manifest.v2+json',
        }
        _image_manifest_config.return_value = (
            't/nova-api:latest',
            manifest,
            config_str
        )
        put_config = self.requests.put(
            'https://192.168.2.1:5000/v2/upload?digest=%s' % config_digest,
            status_code=200
        )
        put_manifest = self.requests.put(
            'https://192.168.2.1:5000/v2/t/nova-api/manifests/latest',
            status_code=200
        )

        self.uploader._copy_local_to_registry(
            source_url=source_url,
            target_url=target_url,
            session=target_session
        )

        _containers_json.assert_called_once_with(
            'overlay-layers', 'layers.json')
        _image_manifest_config.assert_called_once_with('/t/nova-api:latest')
        _copy_layer_local_to_registry.assert_any_call(
            target_url,
            target_session,
            {'digest': 'sha256:aeb786'},
            layers[0]
        )
        _copy_layer_local_to_registry.assert_any_call(
            target_url,
            target_session,
            {'digest': 'sha256:4dc536'},
            layers[1]
        )
        self.assertTrue(put_config.called)
        self.assertTrue(put_manifest.called)

    @mock.patch('os.path.exists')
    def test_containers_file_path(self, mock_exists):
        mock_exists.side_effect = [False, True]

        self.assertRaises(
            ImageUploaderException,
            self.uploader._containers_file_path,
            'overlay-layers',
            'layers.json'
        )
        self.assertEqual(
            '/var/lib/containers/storage/overlay-layers/layers.json',
            self.uploader._containers_file_path(
                'overlay-layers', 'layers.json')
        )

    @mock.patch('os.path.exists')
    def test_containers_file(self, mock_exists):
        mock_exists.return_value = True

        data = '{"config": {}}'
        mock_open = mock.mock_open(read_data=data)
        open_func = 'tripleo_common.image.image_uploader.open'

        with mock.patch(open_func, mock_open):
            self.assertEqual(
                '{"config": {}}',
                self.uploader._containers_file(
                    'overlay-layers', 'layers.json')
            )

    @mock.patch('os.path.exists')
    def test_containers_json(self, mock_exists):
        mock_exists.return_value = True

        data = '{"config": {}}'
        mock_open = mock.mock_open(read_data=data)
        open_func = 'tripleo_common.image.image_uploader.open'

        with mock.patch(open_func, mock_open):
            self.assertEqual(
                {'config': {}},
                self.uploader._containers_json(
                    'overlay-layers', 'layers.json')
            )

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._get_local_layers_manifest')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._containers_json')
    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._containers_file')
    def test_image_manifest_config(self, _containers_file, _containers_json,
                                   _get_local_layers_manifest):
        _containers_file.return_value = '{"config": {}}'
        images_not_found = [{
            'id': 'aaaa',
            'names': ['192.168.2.1:5000/t/heat-api:latest']
        }, {
            'id': 'bbbb',
            'names': ['192.168.2.1:5000/t/heat-engine:latest']
        }]
        images = [{
            'id': 'cccc',
            'names': ['192.168.2.1:5000/t/nova-api:latest']
        }]
        man = {
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': 'application/vnd.docker.container.image.v1+json'
            },
            'layers': [],
        }
        _containers_json.side_effect = [images_not_found, images, man]
        _get_local_layers_manifest.return_value = man

        self.assertRaises(
            ImageNotFoundException,
            self.uploader._image_manifest_config,
            '192.168.2.1:5000/t/nova-api:latest'
        )

        image, manifest, config_str = self.uploader._image_manifest_config(
            '192.168.2.1:5000/t/nova-api:latest'
        )
        self.assertEqual(images[0], image)
        self.assertEqual(man, manifest)
        self.assertEqual('{"config": {}}', config_str)
        _containers_json.assert_has_calls([
            mock.call('overlay-images', 'images.json'),
            mock.call('overlay-images', 'images.json'),
            mock.call('overlay-images', 'cccc', 'manifest')
        ])
        _containers_file.assert_called_once_with(
            'overlay-images', 'cccc', '=c2hhMjU2OjEyMzQ='
        )
        _get_local_layers_manifest.assert_called_once_with(
            man, config_str)

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._get_all_local_layers_by_digest')
    def test_get_local_layers_manifest(self, mock_layers_by_digest):
        mock_layers_by_digest.return_value = {
            'sha256:1': {'diff-size': 8},
            'sha256:2': {'diff-size': 9}
        }
        man = {
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': 'application/vnd.docker.container.image.v1+json'
            },
            'layers': [
                {"digest": "sha256:12345"}
            ]
        }
        config_str = json.dumps({'rootfs':
                                {'diff_ids': ['sha256:1', 'sha256:2']}})

        manifest = self.uploader._get_local_layers_manifest(man, config_str)

        manifest_expected = {
            'config': man['config'],
            'layers': [
                {'digest': 'sha256:1',
                 'mediaType': 'application/vnd.docker.image.rootfs.diff.tar',
                 'size': 8},
                {'digest': 'sha256:2',
                 'mediaType': 'application/vnd.docker.image.rootfs.diff.tar',
                 'size': 9}
            ]
        }

        self.assertEqual(manifest_expected, manifest)

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._get_all_local_layers_by_digest')
    def test_get_local_layers_manifest_missing_rootfs(self,
                                                      mock_layers_by_digest):
        mock_layers_by_digest.return_value = {
            'sha256:1': {'diff-size': 8}
        }
        man = {
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': 'application/vnd.docker.container.image.v1+json'
            },
            'layers': [
                {"digest": "sha256:12345"}
            ]
        }
        manifest = self.uploader._get_local_layers_manifest(man, '{}')

        self.assertEqual(man, manifest)

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._get_all_local_layers_by_digest')
    def test_get_local_layers_manifest_missing_layer(self,
                                                     mock_layers_by_digest):
        mock_layers_by_digest.return_value = {
            'sha256:1': {'diff-size': 8}
        }
        man = {
            'config': {
                'digest': 'sha256:1234',
                'size': 2,
                'mediaType': 'application/vnd.docker.container.image.v1+json'
            },
            'layers': [
                {"digest": "sha256:12345"}
            ]
        }
        config_str = json.dumps({'rootfs':
                                {'diff_ids': ['sha256:3']}})
        self.assertRaises(ImageNotFoundException,
                          self.uploader._get_local_layers_manifest,
                          man,
                          config_str)

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._image_manifest_config')
    def test_inspect(self, _image_manifest_config):
        url = urlparse('containers-storage:/t/nova-api:latest')
        config = {
            'config': {
                'Labels': ['one', 'two']
            },
            'architecture': 'x86_64',
            'os': 'linux'
        }
        _image_manifest_config.return_value = (
            {
                'id': 'cccc',
                'digest': 'sha256:ccccc',
                'names': ['192.168.2.1:5000/t/nova-api:latest'],
                'created': '2018-10-02T11:13:45.567533229Z'
            }, {
                'config': {
                    'digest': 'sha256:1234',
                },
                'layers': [
                    {'digest': 'sha256:aaa'},
                    {'digest': 'sha256:bbb'},
                    {'digest': 'sha256:ccc'}
                ],
            },
            json.dumps(config)
        )

        self.assertEqual(
            {
                'Name': '/t/nova-api',
                'Architecture': 'x86_64',
                'Created': '2018-10-02T11:13:45.567533229Z',
                'Digest': 'sha256:ccccc',
                'DockerVersion': '',
                'Labels': ['one', 'two'],
                'Layers': ['sha256:aaa', 'sha256:bbb', 'sha256:ccc'],
                'Os': 'linux',
                'RepoTags': []
            },
            self.uploader._inspect(url)
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._image_manifest_config')
    def test_inspect_no_labels(self, _image_manifest_config):
        url = urlparse('containers-storage:/t/nova-api:latest')
        config = {
            'config': {},
            'architecture': 'x86_64',
            'os': 'linux'
        }
        _image_manifest_config.return_value = (
            {
                'id': 'cccc',
                'digest': 'sha256:ccccc',
                'names': ['192.168.2.1:5000/t/nova-api:latest'],
                'created': '2018-10-02T11:13:45.567533229Z'
            }, {
                'config': {
                    'digest': 'sha256:1234',
                },
                'layers': [
                    {'digest': 'sha256:aaa'},
                    {'digest': 'sha256:bbb'},
                    {'digest': 'sha256:ccc'}
                ],
            },
            json.dumps(config)
        )

        self.assertEqual(
            {
                'Name': '/t/nova-api',
                'Architecture': 'x86_64',
                'Created': '2018-10-02T11:13:45.567533229Z',
                'Digest': 'sha256:ccccc',
                'DockerVersion': '',
                'Labels': {},
                'Layers': ['sha256:aaa', 'sha256:bbb', 'sha256:ccc'],
                'Os': 'linux',
                'RepoTags': []
            },
            self.uploader._inspect(url)
        )

    @mock.patch('os.environ')
    @mock.patch('subprocess.Popen')
    def test_delete(self, mock_popen, mock_environ):
        url = urlparse('containers-storage:/t/nova-api:latest')
        mock_process = mock.Mock()
        mock_process.communicate.return_value = ('image deleted', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        mock_environ.copy.return_value = {}

        self.assertEqual(
            'image deleted',
            self.uploader._delete(url)
        )
        mock_popen.assert_called_once_with([
            'buildah',
            'rmi',
            '/t/nova-api:latest'],
            env={}, stdout=-1,
            universal_newlines=True
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._delete')
    def test_cleanup(self, _delete):
        self.uploader.cleanup(['foo', 'bar', 'baz'])
        _delete.assert_has_calls([
            mock.call(urlparse('containers-storage:bar')),
            mock.call(urlparse('containers-storage:baz')),
            mock.call(urlparse('containers-storage:foo'))
        ])

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._fetch_manifest')
    def test_collect_manifests_layers(self, _fetch_manifest):
        manifest = {
            'schemaVersion': 2,
            'mediaType': image_uploader.MEDIA_MANIFEST_V2,
            'config': {
                'mediaType': image_uploader.MEDIA_CONFIG,
                'digest': 'sha256:1111'
            },
            'layers': [
                {'digest': 'sha256:2222'},
                {'digest': 'sha256:3333'},
                {'digest': 'sha256:4444'}
            ]
        }
        manifest_str = json.dumps(manifest, indent=2)
        _fetch_manifest.return_value = manifest_str
        url = urlparse('docker://docker.io/t/nova-api:latest')
        session = requests.Session()
        layers = []
        manifests_str = []

        self.uploader._collect_manifests_layers(
            url, session, manifests_str, layers, False)
        self.assertEqual([manifest_str], manifests_str)
        self.assertEqual(
            [
                'sha256:2222',
                'sha256:3333',
                'sha256:4444',
            ],
            layers
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._fetch_manifest')
    def test_collect_manifests_layers_v1(self, _fetch_manifest):
        manifest = {
            'schemaVersion': 1,
            'mediaType': image_uploader.MEDIA_MANIFEST_V1,
            'fsLayers': [
                {'blobSum': 'sha256:4444'},
                {'blobSum': 'sha256:3333'},
                {'blobSum': 'sha256:2222'},
            ]
        }
        manifest_str = json.dumps(manifest, indent=2)
        _fetch_manifest.return_value = manifest_str
        url = urlparse('docker://docker.io/t/nova-api:latest')
        session = requests.Session()
        layers = []
        manifests_str = []

        self.uploader._collect_manifests_layers(
            url, session, manifests_str, layers, False)
        self.assertEqual([manifest_str], manifests_str)
        self.assertEqual(
            [
                'sha256:2222',
                'sha256:3333',
                'sha256:4444',
            ],
            layers
        )

    @mock.patch('tripleo_common.image.image_uploader.'
                'PythonImageUploader._fetch_manifest')
    def test_collect_manifests_layers_multi_arch(self, _fetch_manifest):
        manifest_x86 = {
            'schemaVersion': 2,
            'mediaType': image_uploader.MEDIA_MANIFEST_V2,
            'config': {
                'mediaType': image_uploader.MEDIA_CONFIG,
                'digest': 'sha256:1111'
            },
            'layers': [
                {'digest': 'sha256:2222'},
                {'digest': 'sha256:3333'},
                {'digest': 'sha256:4444'}
            ]
        }
        manifest_ppc = {
            'schemaVersion': 2,
            'mediaType': image_uploader.MEDIA_MANIFEST_V2,
            'config': {
                'mediaType': image_uploader.MEDIA_CONFIG,
                'digest': 'sha256:5555'
            },
            'layers': [
                {'digest': 'sha256:6666'},
                {'digest': 'sha256:7777'},
                {'digest': 'sha256:8888'}
            ]
        }
        manifest = {
            'schemaVersion': 2,
            'mediaType': image_uploader.MEDIA_MANIFEST_V2_LIST,
            "manifests": [
                {
                    "mediaType": image_uploader.MEDIA_MANIFEST_V2,
                    "digest": "sha256:bbbb",
                    "platform": {
                        "architecture": "amd64",
                        "os": "linux",
                        "features": ["sse4"]
                    }
                },
                {
                    "mediaType": image_uploader.MEDIA_MANIFEST_V2,
                    "digest": "sha256:aaaa",
                    "platform": {
                        "architecture": "ppc64le",
                        "os": "linux",
                    }
                }
            ]
        }
        manifest_str = json.dumps(manifest, indent=2)
        _fetch_manifest.side_effect = [
            manifest_str,
            json.dumps(manifest_x86),
            json.dumps(manifest_ppc)
        ]
        url = urlparse('docker://docker.io/t/nova-api:latest')
        session = requests.Session()
        layers = []
        manifests_str = []

        self.uploader._collect_manifests_layers(
            url, session, manifests_str, layers, multi_arch=True)
        self.assertEqual(
            [
                manifest_str,
                json.dumps(manifest_x86),
                json.dumps(manifest_ppc)
            ],
            manifests_str
        )
        self.assertEqual(
            [
                'sha256:2222',
                'sha256:3333',
                'sha256:4444',
                'sha256:6666',
                'sha256:7777',
                'sha256:8888',
            ],
            layers
        )
