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

import base64
from concurrent import futures
import hashlib
import json
import os
import random
import re
import requests
from requests import auth as requests_auth
from requests.adapters import HTTPAdapter
import shutil
import six
from six.moves.urllib import parse
import socket
import subprocess
import tempfile
import tenacity
import yaml

from datetime import datetime
from dateutil.parser import parse as dt_parse
from dateutil.tz import tzlocal
from oslo_concurrency import processutils
from oslo_log import log as logging
from tripleo_common.actions import ansible
from tripleo_common.image.base import BaseImageManager
from tripleo_common.image.exception import ImageNotFoundException
from tripleo_common.image.exception import ImageRateLimitedException
from tripleo_common.image.exception import ImageUploaderException
from tripleo_common.image.exception import ImageUploaderThreadException
from tripleo_common.image import image_export
from tripleo_common.utils import image as image_utils
from tripleo_common.utils.locks import threadinglock


LOG = logging.getLogger(__name__)


SECURE_REGISTRIES = (
    'trunk.registry.rdoproject.org',
    'registry.redhat.io',
    'registry.access.redhat.com',
    'docker.io',
    'registry-1.docker.io',
)

NO_VERIFY_REGISTRIES = ()

CLEANUP = (
    CLEANUP_FULL, CLEANUP_PARTIAL, CLEANUP_NONE
) = (
    'full', 'partial', 'none'
)

CALL_TYPES = (
    CALL_PING,
    CALL_MANIFEST,
    CALL_BLOB,
    CALL_UPLOAD,
    CALL_TAGS,
    CALL_CATALOG
) = (
    '/',
    '%(image)s/manifests/%(tag)s',
    '%(image)s/blobs/%(digest)s',
    '%(image)s/blobs/uploads/',
    '%(image)s/tags/list',
    '/_catalog',
)

MEDIA_TYPES = (
    MEDIA_MANIFEST_V1,
    MEDIA_MANIFEST_V1_SIGNED,
    MEDIA_MANIFEST_V2,
    MEDIA_MANIFEST_V2_LIST,
    MEDIA_OCI_MANIFEST_V1,
    MEDIA_OCI_INDEX_V1,
    MEDIA_CONFIG,
    MEDIA_BLOB,
    MEDIA_BLOB_COMPRESSED
) = (
    'application/vnd.docker.distribution.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v1+prettyjws',
    'application/vnd.docker.distribution.manifest.v2+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.container.image.v1+json',
    'application/vnd.docker.image.rootfs.diff.tar',
    'application/vnd.docker.image.rootfs.diff.tar.gzip'
)

DEFAULT_UPLOADER = 'python'


def get_undercloud_registry():
    ctlplane_hostname = '.'.join([socket.gethostname().split('.')[0],
                                  'ctlplane'])
    cmd = ['getent', 'hosts', ctlplane_hostname]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               universal_newlines=True)
    out, err = process.communicate()

    if process.returncode != 0:
        LOG.warning('No entry for %s in /etc/hosts. Falling back to use the '
                    'default (localhost) undercloud registry.'
                    % ctlplane_hostname)
        address = 'localhost'
    else:
        address = out.split()[1]

    return '%s:%s' % (address, '8787')


class MakeSession(object):
    """Class method to uniformly create sessions.

    Sessions created by this class will retry on errors with an exponential
    backoff before raising an exception. Because our primary interaction is
    with the container registries the adapter will also retry on 401 and
    404. This is being done because registries commonly return 401 when an
    image is not found, which is commonly a cache miss. See the adapter
    definitions for more on retry details.
    """
    def __init__(self, verify=True):
        self.session = requests.Session()
        self.session.verify = verify
        adapter = HTTPAdapter(
            max_retries=8,
            pool_connections=24,
            pool_maxsize=24,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def create(self):
        return self.__enter__()

    def __enter__(self):
        return self.session

    def __exit__(self, *args, **kwargs):
        self.session.close()


class RegistrySessionHelper(object):
    """ Class with various registry session helpers

    This class contains a bunch of static methods to be used when making
    session requests against a container registry. The methods are primarily
    used to handle authentication/reauthentication for the requests against
    registries that require auth.
    """
    @staticmethod
    def check_status(session, request, allow_reauth=True):
        """ Check request status and trigger reauth

        This function can be used to check if we need to perform authentication
        for a container registry request because we've gotten a 401.
        """
        hash_request_id = hashlib.sha1(str(request.url).encode())
        request_id = hash_request_id.hexdigest()
        text = getattr(request, 'text', 'unknown')
        reason = getattr(request, 'reason', 'unknown')
        status_code = getattr(request, 'status_code', None)
        headers = getattr(request, 'headers', {})
        session_headers = getattr(session, 'headers', {})

        if status_code >= 300:
            LOG.info(
                'Non-2xx: id {}, status {}, reason {}, text {}'.format(
                    request_id,
                    status_code,
                    reason,
                    text
                )
            )

        if status_code == 401:
            LOG.warning(
                'Failure: id {}, status {}, reason {} text {}'.format(
                    request_id,
                    status_code,
                    reason,
                    text
                )
            )
            LOG.debug(
                'Request headers after 401: id {}, headers {}'.format(
                    request_id,
                    headers
                )
            )
            LOG.debug(
                'Session headers after 401: id {}, headers {}'.format(
                    request_id,
                    session_headers
                )
            )

            www_auth = headers.get(
                'www-authenticate',
                headers.get(
                    'Www-Authenticate'
                )
            )
            if www_auth:
                error = None
                # Handle docker.io shenanigans. docker.io will return 401
                # for 403 and 404 but provide an error string. Other registries
                # like registry.redhat.io and quay.io do not do this. So if
                # we find an error string, check to see if we should reauth.
                do_reauth = allow_reauth
                if 'error=' in www_auth:
                    error = re.search('error="(.*?)"', www_auth).group(1)
                    LOG.warning(
                        'Error detected in auth headers: error {}'.format(
                            error
                        )
                    )
                    do_reauth = (error == 'invalid_token' and allow_reauth)
                if do_reauth:
                    if hasattr(session, 'reauthenticate'):
                        reauth = int(session.headers.get('_TripleOReAuth', 0))
                        reauth += 1
                        session.headers['_TripleOReAuth'] = str(reauth)
                        LOG.warning(
                            'Re-authenticating: id {}, count {}'.format(
                                request_id,
                                reauth
                            )
                        )
                        session.reauthenticate(**session.auth_args)

        if status_code == 429:
            raise ImageRateLimitedException('Rate Limited while requesting '
                                            '{}'.format(request.url))

        request.raise_for_status()

    @staticmethod
    def check_redirect_trusted(request_response, request_session,
                               stream=True, timeout=30):
        """Check if we've been redirected to a trusted source

        Because we may be using auth, we may not want to leak authentication
        keys to an untrusted source. If we get a redirect, we need to check
        that the redirect url is one of our sources that we trust. Otherwise
        we drop the Authorization header from the redirect request. We'll
        add the header back into the request session after performing the
        request to ensure that future usage of the session.

        :param: request_response: Response object of the request to check
        :param: request_session: Session to use when redirecting
        :param: stream: Should we stream the response of the redirect
        :param: tiemout: Timeout for the redirect request
        """
        # we're not a redirect, just return the original response
        if not (request_response.status_code >= 300
                and request_response.status_code < 400):
            return request_response
        # parse the destination location
        redir_url = parse.urlparse(request_response.headers['Location'])
        # close the response since we're going to replace it
        request_response.close()
        auth_header = request_session.headers.pop('Authorization', None)
        # ok we got a redirect, let's check where we are going
        if len([h for h in SECURE_REGISTRIES if h in redir_url.netloc]) > 0:
            # we're going to a trusted location, add the header back and
            # return response
            request_session.headers.update({'Authorization': auth_header})
            request_response = request_session.get(redir_url.geturl(),
                                                   stream=stream,
                                                   timeout=timeout)
        else:
            # we didn't trust the place we're going, request without auth but
            # add the auth back to the request session afterwards
            request_response = request_session.get(redir_url.geturl(),
                                                   stream=stream,
                                                   timeout=timeout)
            request_session.headers.update({'Authorization': auth_header})

        request_response.encoding = 'utf-8'
        # recheck status here to make sure we didn't get a 401 from
        # our redirect host path.
        RegistrySessionHelper.check_status(session=request_session,
                                           request=request_response)
        return request_response

    @staticmethod
    def get_cached_bearer_token(lock=None, scope=None):
        if not lock:
            return None
        with lock.get_lock():
            data = lock.sessions().get(scope)
            if data and data.get('issued_at'):
                token_time = dt_parse(data.get('issued_at'))
                now = datetime.now(tzlocal())
                expires_in = data.get('expires_in')
                if not expires_in or (now - token_time).seconds < expires_in:
                    return data['token']
        return None

    @staticmethod
    def get_bearer_token(session, lock=None, username=None, password=None,
                         realm=None, service=None, scope=None):
        cached_token = RegistrySessionHelper.get_cached_bearer_token(lock,
                                                                     scope)
        if cached_token:
            return cached_token

        auth = None
        token_param = {}
        if service:
            token_param['service'] = service
        if scope:
            token_param['scope'] = scope
        if username:
            auth = requests.auth.HTTPBasicAuth(username, password)

        auth_req = session.get(realm, params=token_param, auth=auth,
                               timeout=30)
        auth_req.raise_for_status()
        resp = auth_req.json()
        if lock and 'token' in resp:
            with lock.get_lock():
                lock.sessions().update({scope: resp})
        elif lock and 'token' not in resp:
            raise Exception('Invalid auth response, no token provide')
        hash_request_id = hashlib.sha1(str(auth_req.url).encode())
        LOG.debug(
            'Session authenticated: id {}'.format(
                hash_request_id.hexdigest()
            )
        )
        return resp['token']

    @staticmethod
    def parse_www_authenticate(header):
        auth_type = None
        auth_type_match = re.search('^([A-Za-z]*) ', header)
        if auth_type_match:
            auth_type = auth_type_match.group(1)
        if not auth_type:
            return (None, None, None)
        realm = None
        service = None
        if 'realm=' in header:
            realm = re.search('realm="(.*?)"', header).group(1)
        if 'service=' in header:
            service = re.search('service="(.*?)"', header).group(1)
        return (auth_type, realm, service)

    @staticmethod
    @tenacity.retry(  # Retry up to 5 times with longer time for rate limit
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            ImageRateLimitedException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1.5, max=60),
        stop=tenacity.stop_after_attempt(5)
    )
    def _action(action, request_session, *args, **kwargs):
        """ Perform a session action and retry if auth fails

        This function dynamically performs a specific type of call
        using the provided session (get, patch, post, etc). It will
        attempt a single re-authentication if the initial request
        fails with a 401.
        """
        _action = getattr(request_session, action)
        try:
            req = _action(*args, **kwargs)
            RegistrySessionHelper.check_status(session=request_session,
                                               request=req)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                req = _action(*args, **kwargs)
                RegistrySessionHelper.check_status(session=request_session,
                                                   request=req)
            else:
                raise
        return req

    @staticmethod
    def get(request_session, *args, **kwargs):
        """ Perform a get and retry if auth fails

        This function is designed to be used when we perform a get to
        an authenticated source. This function will attempt a single
        re-authentication request if the first one fails.
        """
        return RegistrySessionHelper._action('get',
                                             request_session,
                                             *args,
                                             **kwargs)

    @staticmethod
    def patch(request_session, *args, **kwargs):
        """ Perform a patch and retry if auth fails

        This function is designed to be used when we perform a path to
        an authenticated source. This function will attempt a single
        re-authentication request if the first one fails.
        """
        return RegistrySessionHelper._action('patch',
                                             request_session,
                                             *args,
                                             **kwargs)

    @staticmethod
    def post(request_session, *args, **kwargs):
        """ Perform a post and retry if auth fails

        This function is designed to be used when we perform a post to
        an authenticated source. This function will attempt a single
        re-authentication request if the first one fails.
        """
        return RegistrySessionHelper._action('post',
                                             request_session,
                                             *args,
                                             **kwargs)

    @staticmethod
    def put(request_session, *args, **kwargs):
        """ Perform a put and retry if auth fails

        This function is designed to be used when we perform a put to
        an authenticated source. This function will attempt a single
        re-authentication request if the first one fails.
        """
        return RegistrySessionHelper._action('put',
                                             request_session,
                                             *args,
                                             **kwargs)


class ImageUploadManager(BaseImageManager):
    """Manage the uploading of image files

       Manage the uploading of images from a config file specified in YAML
       syntax. Multiple config files can be specified. They will be merged.
       """

    def __init__(self, config_files=None,
                 cleanup=CLEANUP_FULL,
                 mirrors=None, registry_credentials=None,
                 multi_arch=False, lock=None):
        if config_files is None:
            config_files = []
        super(ImageUploadManager, self).__init__(config_files)
        self.uploaders = {
            'skopeo': SkopeoImageUploader(),
            'python': PythonImageUploader()
        }
        self.uploaders['python'].init_global_state(lock)
        self.cleanup = cleanup
        if mirrors:
            for uploader in self.uploaders.values():
                if hasattr(uploader, 'mirrors'):
                    uploader.mirrors.update(mirrors)
        if registry_credentials:
            self.validate_registry_credentials(registry_credentials)
            for uploader in self.uploaders.values():
                uploader.registry_credentials = registry_credentials
        self.multi_arch = multi_arch

    @staticmethod
    def validate_registry_credentials(creds_data):
        if not isinstance(creds_data, dict):
            raise TypeError('Credentials data must be a dict')
        for registry, cred_entry in creds_data.items():
            if not isinstance(cred_entry, dict) or len(cred_entry) != 1:
                raise TypeError('Credentials entry must be '
                                'a dict with a single item')
            if not isinstance(registry, six.string_types):
                raise TypeError('Key must be a registry host string: %s' %
                                registry)
            username, password = next(iter(cred_entry.items()))
            if not (isinstance(username, six.string_types) and
                    isinstance(password, six.string_types)):
                raise TypeError('Username and password must be strings: %s' %
                                username)

    def discover_image_tag(self, image, tag_from_label=None,
                           username=None, password=None):
        uploader = self.uploader(DEFAULT_UPLOADER)
        return uploader.discover_image_tag(
            image, tag_from_label=tag_from_label,
            username=username, password=password)

    def uploader(self, uploader):
        if uploader not in self.uploaders:
            raise ImageUploaderException('Unknown image uploader type')
        return self.uploaders[uploader]

    def get_uploader(self, uploader):
        return self.uploader(uploader)

    @staticmethod
    def get_push_destination(item):
        push_destination = item.get('push_destination')
        if not push_destination:
            return get_undercloud_registry()

        # If set to True, use discovered undercloud registry
        if isinstance(push_destination, bool):
            return get_undercloud_registry()

        return push_destination

    def upload(self):
        """Start the upload process"""

        LOG.info('Using config files: %s' % self.config_files)

        uploads = self.load_config_files(self.UPLOADS) or []
        container_images = self.load_config_files(self.CONTAINER_IMAGES) or []
        upload_images = uploads + container_images

        tasks = []
        for item in upload_images:
            image_name = item.get('imagename')
            uploader = item.get('uploader', DEFAULT_UPLOADER)
            pull_source = item.get('pull_source')
            push_destination = self.get_push_destination(item)

            # This updates the parsed upload_images dict with real values
            item['push_destination'] = push_destination
            append_tag = item.get('modify_append_tag')
            modify_role = item.get('modify_role')
            modify_vars = item.get('modify_vars')
            multi_arch = item.get('multi_arch', self.multi_arch)

            uploader = self.uploader(uploader)
            tasks.append(UploadTask(
                image_name, pull_source, push_destination,
                append_tag, modify_role, modify_vars,
                self.cleanup, multi_arch))

        # NOTE(mwhahaha): We want to randomize the upload process because of
        # the shared nature of container layers. Because we multiprocess the
        # handling of containers, if performed in an alphabetical order (the
        # default) we end up duplicating fetching of container layers. Things
        # Like cinder-volume and cinder-backup share almost all of the same
        # layers so when they are fetched at the same time, we will duplicate
        # the processing. By randomizing the list we will reduce the amount
        # of duplicating that occurs. In my testing I went from ~30mins to
        # ~20mins to run. In the future this could be improved if we added
        # some locking to the container fetching based on layer hashes but
        # will require a significant rewrite.
        random.shuffle(tasks)
        for task in tasks:
            uploader.add_upload_task(task)

        for uploader in self.uploaders.values():
            uploader.run_tasks()

        return upload_images  # simply to make test validation easier


class BaseImageUploader(object):
    lock = None
    mirrors = {}
    insecure_registries = set()
    no_verify_registries = set(NO_VERIFY_REGISTRIES)
    secure_registries = set(SECURE_REGISTRIES)
    export_registries = set()
    push_registries = set()

    def __init__(self):
        self.upload_tasks = []
        # A mapping of layer hashs to the image which first copied that
        # layer to the target
        self.image_layers = {}
        self.registry_credentials = {}

    @classmethod
    def init_registries_cache(cls):
        cls.insecure_registries.clear()
        cls.no_verify_registries.clear()
        cls.no_verify_registries.update(NO_VERIFY_REGISTRIES)
        cls.secure_registries.clear()
        cls.secure_registries.update(SECURE_REGISTRIES)
        cls.mirrors.clear()
        cls.export_registries.clear()
        cls.push_registries.clear()

    def cleanup(self):
        pass

    def run_tasks(self):
        pass

    def credentials_for_registry(self, registry):
        creds = self.registry_credentials.get(registry)
        if not creds:
            return None, None
        username, password = next(iter(creds.items()))
        return username, password

    @classmethod
    def run_modify_playbook(cls, modify_role, modify_vars,
                            source_image, target_image, append_tag,
                            container_build_tool='buildah'):
        run_vars = {}
        if modify_vars:
            run_vars.update(modify_vars)
        run_vars['source_image'] = source_image
        run_vars['target_image'] = target_image
        run_vars['modified_append_tag'] = append_tag
        run_vars['container_build_tool'] = container_build_tool
        LOG.info('Playbook variables: \n%s' % yaml.safe_dump(
            run_vars, default_flow_style=False))
        playbook = [{
            'hosts': 'localhost',
            'gather_facts': 'no',
            'tasks': [{
                'name': 'Import role %s' % modify_role,
                'import_role': {
                    'name': modify_role
                },
                'vars': run_vars
            }]
        }]
        LOG.info('Playbook: \n%s' % yaml.safe_dump(
            playbook, default_flow_style=False))
        work_dir = tempfile.mkdtemp(prefix='tripleo-modify-image-playbook-')
        log_name = 'tripleo-container-image-prepare-ansible.log'
        try:
            for handler in LOG.logger.root.handlers:
                if hasattr(handler, 'baseFilename'):
                    if os.path.isfile(handler.baseFilename):
                        log_f = os.path.join(
                            os.path.dirname(handler.baseFilename),
                            log_name
                        )
                        break
            else:
                raise OSError('Log output is not a file.')
        except (AttributeError, OSError):
            log_f = os.path.join('/var/log', log_name)
        try:
            LOG.info('Ansible action starting')
            ansible.AnsiblePlaybookAction(
                playbook=playbook,
                work_dir=work_dir,
                verbosity=1,
                extra_env_variables=dict(os.environ),
                override_ansible_cfg=(
                    "[defaults]\n"
                    "stdout_callback=tripleo_dense\n"
                    "log_path=%s\n" % log_f
                )
            ).run(None)
        except processutils.ProcessExecutionError as e:
            LOG.error(
                '%s\n'
                'Error running playbook in directory: %s\n'
                'Playbook log information can be reviewed here: %s' % (
                    e.stdout,
                    work_dir,
                    log_f
                )
            )
            raise ImageUploaderException(
                'Modifying image %s failed' % target_image
            )
        else:
            LOG.info('Ansible action completed')
        finally:
            shutil.rmtree(work_dir)

    @classmethod
    def _images_match(cls, image1, image2, session1=None):
        try:
            image1_digest = cls._image_digest(image1, session=session1)
        except Exception:
            return False
        try:
            image2_digest = cls._image_digest(image2)
        except Exception:
            return False

        # missing digest, no way to know if they match
        if not image1_digest or not image2_digest:
            return False
        return image1_digest == image2_digest

    @classmethod
    def _image_digest(cls, image, session=None):
        image_url = cls._image_to_url(image)
        i = cls._inspect(image_url, session)
        return i.get('Digest')

    @classmethod
    def _image_labels(cls, image_url, session=None):
        i = cls._inspect(image_url, session)
        return i.get('Labels', {}) or {}

    @classmethod
    def _image_exists(cls, image, session=None):
        try:
            cls._image_digest(
                image, session=session)
        except ImageNotFoundException:
            return False
        else:
            return True

    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def authenticate(self, image_url, username=None, password=None,
                     session=None):
        netloc = image_url.netloc
        image, tag = self._image_tag_from_url(image_url)
        scope = 'repository:%s:pull' % image[1:]

        self.is_insecure_registry(registry_host=netloc)
        url = self._build_url(image_url, path='/')
        verify = (netloc not in self.no_verify_registries)
        if not session:
            session = MakeSession(verify=verify).create()
        else:
            session.headers.pop('Authorization', None)
            session.verify = verify

        cached_token = None
        if getattr(self, 'lock', None):
            cached_token = RegistrySessionHelper.\
                get_cached_bearer_token(self.lock, scope)

        if cached_token:
            session.headers['Authorization'] = 'Bearer %s' % cached_token

        r = session.get(url, timeout=30)
        LOG.debug('%s status code %s' % (url, r.status_code))
        if r.status_code == 200:
            return session
        if r.status_code != 401:
            r.raise_for_status()
        if 'www-authenticate' not in r.headers:
            raise ImageUploaderException(
                'Unknown authentication method for headers: %s' % r.headers)

        auth = None
        www_auth = r.headers['www-authenticate']
        token_param = {}

        (auth_type, realm, service) = \
            RegistrySessionHelper.parse_www_authenticate(www_auth)

        if auth_type and auth_type.lower() == 'bearer':
            LOG.debug('Using bearer token auth')
            if getattr(self, 'lock', None):
                lock = self.lock
            else:
                lock = None
            token = RegistrySessionHelper.get_bearer_token(session, lock=lock,
                                                           username=username,
                                                           password=password,
                                                           realm=realm,
                                                           service=service,
                                                           scope=scope)
        elif auth_type and auth_type.lower() == 'basic':
            LOG.debug('Using basic auth')
            if not username or not password:
                raise Exception('Authentication credentials required for '
                                'basic auth: %s' % url)
            auth = requests_auth.HTTPBasicAuth(username, password)
            rauth = session.get(url, params=token_param, auth=auth, timeout=30)
            rauth.raise_for_status()
            token = (
                base64.b64encode(
                    bytes(username + ':' + password, 'utf-8')).decode('ascii')
            )
            hash_request_id = hashlib.sha1(str(rauth.url).encode())
            LOG.debug(
                'Session authenticated: id {}'.format(
                    hash_request_id.hexdigest()
                )
            )
        else:
            raise ImageUploaderException(
                'Unknown www-authenticate value: %s' % www_auth)
        auth_header = '%s %s' % (auth_type, token)
        session.headers['Authorization'] = auth_header

        setattr(session, 'reauthenticate', self.authenticate)
        setattr(
            session,
            'auth_args',
            dict(
                image_url=image_url,
                username=username,
                password=password,
                session=session
            )
        )
        return session

    @staticmethod
    def _get_response_text(response, encoding='utf-8', force_encoding=False):
        """Return request response text

        We need to set the encoding for the response other wise it
        will attempt to detect the encoding which is very time consuming.
        See https://github.com/psf/requests/issues/4235 for additional
        context.

        :param: response: requests Respoinse object
        :param: encoding: encoding to set if not currently set
        :param: force_encoding: set response encoding always
        """

        if force_encoding or not response.encoding:
            response.encoding = encoding
        return response.text

    @classmethod
    def _build_url(cls, url, path):
        netloc = url.netloc
        if netloc in cls.mirrors:
            mirror = cls.mirrors[netloc]
            return '%sv2%s' % (mirror, path)
        else:
            if (cls.is_insecure_registry(registry_host=netloc) and
                    netloc not in cls.no_verify_registries):
                scheme = 'http'
            else:
                scheme = 'https'
            if netloc == 'docker.io':
                netloc = 'registry-1.docker.io'
            return '%s://%s/v2%s' % (scheme, netloc, path)

    @classmethod
    def _image_tag_from_url(cls, image_url):
        if '@' in image_url.path:
            parts = image_url.path.split('@')
        else:
            parts = image_url.path.split(':')
        tag = parts[-1]
        image = ':'.join(parts[:-1])
        return image, tag

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _inspect(cls, image_url, session=None, default_tag=False):
        image, tag = cls._image_tag_from_url(image_url)
        parts = {
            'image': image,
            'tag': tag
        }

        tags_url = cls._build_url(
            image_url, CALL_TAGS % parts
        )
        tags_r = RegistrySessionHelper.get(session, tags_url, timeout=30)
        tags = tags_r.json()['tags']
        if default_tag and tag not in tags:
            if tags:
                parts['tag'] = tags[-1]
            else:
                raise ImageNotFoundException('Not found image: %s' %
                                             image_url.geturl())

        manifest_url = cls._build_url(
            image_url, CALL_MANIFEST % parts
        )
        manifest_headers = {'Accept': MEDIA_MANIFEST_V2}

        try:
            manifest_r = RegistrySessionHelper.get(
                session,
                manifest_url,
                headers=manifest_headers,
                timeout=30
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (403, 404):
                raise ImageNotFoundException('Not found image: %s' %
                                             image_url.geturl())
            else:
                raise

        manifest_str = cls._get_response_text(manifest_r)

        if 'Docker-Content-Digest' in manifest_r.headers:
            digest = manifest_r.headers['Docker-Content-Digest']
        else:
            # The registry didn't supply the manifest digest, so calculate it
            calc_digest = hashlib.sha256()
            calc_digest.update(manifest_str.encode('utf-8'))
            digest = 'sha256:%s' % calc_digest.hexdigest()

        manifest = json.loads(manifest_str)

        if manifest.get('schemaVersion', 2) == 1:
            config = json.loads(manifest['history'][0]['v1Compatibility'])
            layers = list(reversed([x['blobSum']
                                    for x in manifest['fsLayers']]))
        else:
            layers = [x['digest'] for x in manifest['layers']]

            parts['digest'] = manifest['config']['digest']
            config_headers = {
                'Accept': manifest['config']['mediaType']
            }
            config_url = cls._build_url(
                image_url, CALL_BLOB % parts)
            config_r = RegistrySessionHelper.get(
                session,
                config_url,
                headers=config_headers,
                timeout=30,
                allow_redirects=False
            )
            # check if the blob is a redirect
            config_r = RegistrySessionHelper.check_redirect_trusted(
                config_r, session, stream=False)
            config = config_r.json()

        image, tag = cls._image_tag_from_url(image_url)
        name = '%s%s' % (image_url.netloc, image)
        created = config['created']
        docker_version = config.get('docker_version', '')
        labels = config['config'].get('Labels', {})
        # NOTE: labels can be null
        if labels is None:
            labels = {}
        architecture = config['architecture']
        image_os = config['os']

        return {
            'Name': name,
            'Tag': tag,
            'Digest': digest,
            'RepoTags': tags,
            'Created': created,
            'DockerVersion': docker_version,
            'Labels': labels,
            'Architecture': architecture,
            'Os': image_os,
            'Layers': layers,
        }

    def list(self, registry, session=None):
        self.is_insecure_registry(registry_host=registry)
        url = self._image_to_url(registry)
        catalog_url = self._build_url(
            url, CALL_CATALOG
        )
        catalog_resp = session.get(catalog_url, timeout=30)
        if catalog_resp.status_code in [200]:
            catalog = catalog_resp.json()
        elif catalog_resp.status_code in [404]:
            # just return since the catalog returned a 404
            LOG.debug('catalog_url return 404')
            return []
        else:
            raise ImageUploaderException(
                'Image registry made invalid response: %s' %
                catalog_resp.status_code
            )

        tags_get_args = []
        for repo in catalog.get('repositories', []):
            image = '%s/%s' % (registry, repo)
            tags_get_args.append((self, image, session))

        images = []
        workers = min(max(2, processutils.get_worker_count() // 2), 8)
        with futures.ThreadPoolExecutor(max_workers=workers) as p:
            for image, tags in p.map(tags_for_image, tags_get_args):
                if not tags:
                    continue
                for tag in tags:
                    images.append('%s:%s' % (image, tag))
        return images

    def inspect(self, image, session=None):
        image_url = self._image_to_url(image)
        return self._inspect(image_url, session)

    def delete(self, image, session=None):
        image_url = self._image_to_url(image)
        return self._delete(image_url, session)

    @classmethod
    def _delete(cls, image, session=None):
        raise NotImplementedError()

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _tags_for_image(cls, image, session):
        url = cls._image_to_url(image)
        parts = {
            'image': url.path,
        }
        tags_url = cls._build_url(
            url, CALL_TAGS % parts
        )
        r = session.get(tags_url, timeout=30)
        if r.status_code in (403, 404):
            return image, []
        tags = r.json()
        return image, tags.get('tags', [])

    @classmethod
    def _image_to_url(cls, image):
        if '://' not in image:
            image = 'docker://' + image
        url = parse.urlparse(image)
        return url

    @classmethod
    def _discover_tag_from_inspect(cls, i, image, tag_from_label=None,
                                   fallback_tag=None):
        labels = i.get('Labels', {})

        if hasattr(labels, 'keys'):
            label_keys = ', '.join(labels.keys())
        else:
            label_keys = ""

        if not tag_from_label:
            raise ImageUploaderException(
                'No label specified. Available labels: %s' % label_keys
            )

        if "{" in tag_from_label:
            try:
                tag_label = tag_from_label.format(**labels)
            except ValueError as e:
                raise ImageUploaderException(e)
            except (KeyError, TypeError) as e:
                if fallback_tag:
                    tag_label = fallback_tag
                else:
                    raise ImageUploaderException(
                        'Image %s %s. Available labels: %s' %
                        (image, e, label_keys)
                    )
        else:
            tag_label = None
            if isinstance(labels, dict):
                tag_label = labels.get(tag_from_label)
            if tag_label is None:
                if fallback_tag:
                    tag_label = fallback_tag
                else:
                    raise ImageUploaderException(
                        'Image %s has no label %s. Available labels: %s' %
                        (image, tag_from_label, label_keys)
                    )

        # confirm the tag exists by checking for an entry in RepoTags
        repo_tags = i.get('RepoTags', [])
        if tag_label not in repo_tags:
            raise ImageUploaderException(
                'Image %s has no tag %s.\nAvailable tags: %s' %
                (image, tag_label, ', '.join(repo_tags))
            )
        return tag_label

    def discover_image_tags(self, images, tag_from_label=None,
                            default_tag=False):
        image_urls = [self._image_to_url(i) for i in images]

        # prime self.insecure_registries by testing every image
        for url in image_urls:
            self.is_insecure_registry(registry_host=url)

        discover_args = []
        for image in images:
            discover_args.append((self, image, tag_from_label,
                                  default_tag))

        versioned_images = {}
        with futures.ThreadPoolExecutor(max_workers=16) as p:
            for image, versioned_image in p.map(discover_tag_from_inspect,
                                                discover_args):
                versioned_images[image] = versioned_image
        return versioned_images

    def discover_image_tag(self, image, tag_from_label=None,
                           fallback_tag=None, username=None, password=None):
        image_url = self._image_to_url(image)
        self.is_insecure_registry(registry_host=image_url.netloc)
        try:
            session = self.authenticate(
                image_url, username=username, password=password)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ImageUploaderException(
                    'Unable to authenticate. This may indicate '
                    'missing registry credentials or the provided '
                    'container or namespace does not exist. %s' % e)
            raise

        i = self._inspect(image_url, session)
        return self._discover_tag_from_inspect(i, image, tag_from_label,
                                               fallback_tag)

    def filter_images_with_labels(self, images, labels,
                                  username=None, password=None):
        images_with_labels = []
        for image in images:
            url = self._image_to_url(image)
            self.is_insecure_registry(registry_host=url.netloc)
            try:
                session = self.authenticate(
                    url, username=username, password=password)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    raise ImageUploaderException(
                        'Unable to authenticate. This may indicate '
                        'missing registry credentials or the provided '
                        'container or namespace does not exist. %s' % e)
                raise
            image_labels = self._image_labels(
                url, session=session)
            # The logic is the following: if one of the labels in
            # modify_only_with_labels parameter is present in the image, it
            # will match and add the images that need to be modified.
            for label in labels:
                if label in image_labels:
                    # we found a matching label, adding the image
                    # and leave the loop.
                    images_with_labels.append(image)
                    break

        return images_with_labels

    def add_upload_task(self, task):
        if task.modify_role and task.multi_arch:
            raise ImageUploaderException(
                'Cannot run a modify role on multi-arch image %s' %
                task.image_name
            )
        # prime insecure_registries
        if task.pull_source:
            self.is_insecure_registry(
                registry_host=self._image_to_url(task.pull_source).netloc
            )
        else:
            self.is_insecure_registry(
                registry_host=self._image_to_url(task.image_name).netloc
            )
        self.is_insecure_registry(
            registry_host=self._image_to_url(task.push_destination).netloc
        )
        self.upload_tasks.append((self, task))

    @classmethod
    def is_insecure_registry(cls, registry_host):
        if registry_host in cls.secure_registries:
            return False
        if (registry_host in cls.insecure_registries or
                registry_host in cls.no_verify_registries):
            return True
        with requests.Session() as s:
            try:
                s.get('https://%s/v2' % registry_host, timeout=30)
            except requests.exceptions.SSLError:
                # Might be just a TLS certificate validation issue
                # Just retry without the verification
                try:
                    s.get('https://%s/v2' % registry_host, timeout=30,
                          verify=False)
                    cls.no_verify_registries.add(registry_host)
                    # Techinically these type of registries are insecure when
                    # the container engine tries to do a pull. The python
                    # uploader ignores the certificate problem, but they are
                    # still inscure so we return True here while we'll still
                    # use https when we access the registry. LP#1833751
                    return True
                except requests.exceptions.SSLError:
                    # So nope, it's really not a certificate verification issue
                    cls.insecure_registries.add(registry_host)
                    return True
            except Exception:
                # for any other error assume it is a secure registry, because:
                # - it is secure registry
                # - the host is not accessible
                pass
        cls.secure_registries.add(registry_host)
        return False

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _cross_repo_mount(cls, target_image_url, image_layers,
                          source_layers, session):
        netloc = target_image_url.netloc
        name = target_image_url.path.split(':')[0][1:]
        export = netloc in cls.export_registries
        if export:
            # pylint: disable=no-member
            linked_layers = image_export.cross_repo_mount(
                target_image_url, image_layers, source_layers,
                uploaded_layers=cls._global_view_proxy())
            # track linked layers globally for future references
            for layer, info in linked_layers.items():
                # pylint: disable=no-member
                cls._track_uploaded_layers(
                    layer, known_path=info['known_path'],
                    image_ref=info['ref_image'], scope='local')
            return

        if netloc in cls.insecure_registries:
            scheme = 'http'
        else:
            scheme = 'https'
        url = '%s://%s/v2/%s/blobs/uploads/' % (scheme, netloc, name)

        for layer in source_layers:
            # pylint: disable=no-member
            known_path, existing_name = image_utils.uploaded_layers_details(
                cls._global_view_proxy(), layer, scope='remote')
            if layer not in image_layers and not existing_name:
                continue
            if not existing_name:
                existing_name = image_layers[layer].path.split(':')[0][1:]
            if existing_name != name:
                LOG.debug('[%s] Layer %s ref. by image %s already exists '
                          'at %s' % (name, layer, existing_name, known_path))
            LOG.info('[%s] Cross repository blob mount from %s' %
                     (layer, existing_name))
            data = {
                'mount': layer,
                'from': existing_name
            }
            r = RegistrySessionHelper.post(session, url, data=data, timeout=30)
            LOG.debug('%s %s' % (r.status_code, r.reason))


class SkopeoImageUploader(BaseImageUploader):
    """Upload images using skopeo copy"""

    def upload_image(self, task):
        t = task
        LOG.info('[%s] Got imagename' % t.image_name)

        source_image_local_url = parse.urlparse('containers-storage:%s'
                                                % t.source_image)

        target_image_local_url = parse.urlparse('containers-storage:%s' %
                                                t.target_image)

        target_username, target_password = self.credentials_for_registry(
            t.target_image_url.netloc)
        target_session = self.authenticate(
            t.target_image_url,
            username=target_username,
            password=target_password
        )

        image_exists = False
        try:
            image_exists = self._image_exists(t.target_image,
                                              target_session)
        except Exception:
            LOG.warning('[%s] Failed to check if the target '
                        'image exists' % t.target_image)
            pass
        if t.modify_role and image_exists:
            LOG.warning('[%s] Skipping upload for modified '
                        'image' % t.target_image)
            target_session.close()
            return []

        # Keep the target session open yet
        source_username, source_password = self.credentials_for_registry(
            t.source_image_url.netloc)
        source_session = self.authenticate(
            t.source_image_url,
            username=source_username,
            password=source_password
        )
        try:
            source_inspect = self._inspect(
                t.source_image_url,
                session=source_session)
            source_layers = source_inspect.get('Layers', [])
            self._cross_repo_mount(
                t.target_image_url, self.image_layers, source_layers,
                session=target_session)
        except Exception:
            LOG.error('[%s] Failed uploading the target '
                      'image' % t.target_image)
            raise
        finally:
            source_session.close()
            target_session.close()

        to_cleanup = []

        if t.modify_role:

            # Copy from source registry to local storage
            self._copy(
                t.source_image_url,
                source_image_local_url,
            )
            if t.cleanup in (CLEANUP_FULL, CLEANUP_PARTIAL):
                to_cleanup = [t.source_image]

            self.run_modify_playbook(
                t.modify_role, t.modify_vars, t.source_image,
                t.target_image_source_tag, t.append_tag,
                container_build_tool='buildah')
            if t.cleanup == CLEANUP_FULL:
                to_cleanup.append(t.target_image)

            # Copy from local storage to target registry
            self._copy(
                target_image_local_url,
                t.target_image_url,
            )
            LOG.warning('[%s] Completed modify and upload for '
                        'image' % t.image_name)
        else:
            self._copy(
                t.source_image_url,
                t.target_image_url,
            )
            LOG.warning('[%s] Completed upload for image' % t.image_name)
        for layer in source_layers:
            self.image_layers.setdefault(layer, t.target_image_url)
        return to_cleanup

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _copy(cls, source_url, target_url):
        source = source_url.geturl()
        target = target_url.geturl()
        LOG.info('Copying from %s to %s' % (source, target))
        cmd = ['skopeo', 'copy']

        if source_url.netloc in [cls.insecure_registries,
                                 cls.no_verify_registries]:
            cmd.append('--src-tls-verify=false')

        if target_url.netloc in [cls.insecure_registries,
                                 cls.no_verify_registries]:
            cmd.append('--dest-tls-verify=false')

        cmd.append(source)
        cmd.append(target)
        LOG.info('Running %s' % ' '.join(cmd))
        env = os.environ.copy()
        try:
            process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                       universal_newlines=True)

            out, err = process.communicate()
            LOG.info(out)
            if process.returncode != 0:
                raise ImageUploaderException('Error copying image:\n%s\n%s' %
                                             (' '.join(cmd), err))
        except KeyboardInterrupt:
            raise Exception('Action interrupted with ctrl+c')
        return out

    def _delete(self, image_url, session=None):
        insecure = self.is_insecure_registry(registry_host=image_url.netloc)
        image = image_url.geturl()
        LOG.info('[%s] Deleting image' % image)
        cmd = ['skopeo', 'delete']

        if insecure:
            cmd.append('--tls-verify=false')
        cmd.append(image)
        LOG.info('Running %s' % ' '.join(cmd))
        env = os.environ.copy()
        try:
            process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                       universal_newlines=True)

            out, err = process.communicate()
            LOG.info(out.decode('utf-8'))
            if process.returncode != 0:
                raise ImageUploaderException('Error deleting image:\n%s\n%s' %
                                             (' '.join(cmd), err))
        except KeyboardInterrupt:
            raise Exception('Action interrupted with ctrl+c')
        return out

    def cleanup(self, local_images):
        if not local_images:
            return []

        for image in sorted(local_images):
            if not image:
                continue
            LOG.warning('[%s] Removing local copy of image' % image)
            image_url = parse.urlparse('containers-storage:%s' % image)
            self._delete(image_url)

    def run_tasks(self):
        if not self.upload_tasks:
            return
        local_images = []

        # Pull a single image first, to avoid duplicate pulls of the
        # same base layers
        local_images.extend(upload_task(args=self.upload_tasks.pop()))

        # workers will be half the CPU count, to a minimum of 2
        workers = max(2, (processutils.get_worker_count() - 1))
        with futures.ThreadPoolExecutor(max_workers=workers) as p:
            for result in p.map(upload_task, self.upload_tasks):
                local_images.extend(result)
        LOG.info('result %s' % local_images)

        # Do cleanup after all the uploads so common layers don't get deleted
        # repeatedly
        self.cleanup(local_images)


class PythonImageUploader(BaseImageUploader):
    """Upload images using a direct implementation of the registry API"""

    uploaded_layers = {}  # provides global view for multi-threading workers
    lock = None  # provides global locking info plus global view, if MP is used

    @classmethod
    def init_global_state(cls, lock):
        if not cls.lock:
            cls.lock = lock

    @classmethod
    @tenacity.retry(  # Retry until we no longer have collisions
        retry=tenacity.retry_if_exception_type(ImageUploaderThreadException),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10)
    )
    def _layer_fetch_lock(cls, layer):
        if not cls.lock:
            LOG.warning('No lock information provided for layer %s' % layer)
            return
        if layer in cls.lock.objects():
            LOG.debug('[%s] Layer is being fetched by another thread' % layer)
            raise ImageUploaderThreadException('layer being fetched')
        known_path, image = image_utils.uploaded_layers_details(
            cls._global_view_proxy(), layer, scope='local')
        if not known_path or not image:
            known_path, image = image_utils.uploaded_layers_details(
                cls._global_view_proxy(), layer, scope='remote')
        if image and known_path:
            # already processed layers needs no further locking
            return
        with cls.lock.get_lock():
            if layer in cls.lock.objects():
                LOG.debug('Collision for lock %s' % layer)
                raise ImageUploaderThreadException('layer conflict')
            cls.lock.objects().append(layer)
        LOG.debug('Got lock on layer %s' % layer)

    @classmethod
    def _layer_fetch_unlock(cls, layer):
        if not cls.lock:
            LOG.warning('No lock information provided for layer %s' % layer)
            return
        with cls.lock.get_lock():
            while layer in cls.lock.objects():
                cls.lock.objects().remove(layer)
        LOG.debug('Released lock on layer %s' % layer)

    @classmethod
    def _global_view_proxy(cls, value=None, forget=False):
        """Represent the global view for mixed multi-workers concurrent access

        Depending on worker's context target the corresponding shared data
        structures (global view) for the requested value add/remove
        operation. Also keep that global view always consolidated for all of
        the supported MP/MT worker types. Threads will share common data via
        its common class namespace in the threads-safe standard dictionary.
        Processes will use multiprocess synchronization primitives stored in
        the global lock context.

        :param: value: Shared data to track in the global view
        :param: forget: Defines either to add or remove the shared data
        """
        if not cls.lock:
            LOG.warning('No lock information provided for value %s' % value)
            return
        with cls.lock.get_lock():
            if value and forget:
                cls.uploaded_layers.pop(value, None)
                if hasattr(cls.lock, '_global_view'):
                    cls.lock._global_view.pop(value, None)
            elif value:
                cls.uploaded_layers.update(value)
                if hasattr(cls.lock, '_global_view'):
                    cls.lock._global_view.update(value)

        if not value:
            # return global view consolidated among MP/MT workers state
            if hasattr(cls.lock, '_global_view'):
                consolidated_view = cls.uploaded_layers.copy()
                consolidated_view.update(cls.lock._global_view)
                return consolidated_view
            else:
                return cls.uploaded_layers

    @classmethod
    def _track_uploaded_layers(cls, layer, known_path=None, image_ref=None,
                               forget=False, scope='remote'):
        """Track an image layer info in the global view

        Adds or removes layer info to/from the global view shared among
        all workers of all supported types (MP/MT). An image layer hash and
        scope pair provide a unique one-way entry tracked in the global view.
        The layer info being forgotten will be untracked by any existing scope.

        :param: layer: A container image layer hash to track in the global view
        :param: known_path: Known URL or local path for the tracked layer
        :param: image_ref: Name of the image cross-referencing tracked layer
        :param: forget: Defines either to add or remove the tracked layer info
        :param: scope: Specifies remote or local type of the tracked image
        """
        if forget:
            LOG.debug('Untracking processed layer %s for any scope' % layer)
            cls._global_view_proxy(value=layer, forget=True)
        else:
            LOG.debug('Tracking processed layer %s for %s scope'
                      % (layer, scope))
            cls._global_view_proxy(
                value={layer: {scope: {'ref': image_ref, 'path': known_path}}})

    def upload_image(self, task):
        """Upload image from a task

        This function takes an UploadTask and pushes it to the appropriate
        target destinations. It should be noted that if the source container
        is prefix with 'containers-storage:' instead of 'docker://' or no
        prefix, this process will assume that the source container is already
        local to the system.  The local container upload does not currently
        support any of the modification actions. In order to run the
        modification actions on a container prior to upload, the source must
        be a remote image.  Additionally, cleanup has no affect when
        uploading a local image as well.

        :param: task: UploadTask with container information
        """
        t = task
        LOG.info('[%s] Starting upload image process' % t.image_name)

        source_local = t.source_image.startswith('containers-storage:')
        target_image_local_url = parse.urlparse('containers-storage:%s' %
                                                t.target_image)
        target_username, target_password = self.credentials_for_registry(
            t.target_image_url.netloc)
        try:
            target_session = self.authenticate(
                t.target_image_url,
                username=target_username,
                password=target_password
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ImageUploaderException(
                    'Unable to authenticate. This may indicate '
                    'missing registry credentials or the provided '
                    'container or namespace does not exist. %s' % e)
            raise

        try:
            self._detect_target_export(t.target_image_url, target_session)
        except Exception:
            LOG.error('[%s] Failed uploading the target '
                      'image' % t.target_image)
            # Close the session before raising it for more of retrying perhaps
            target_session.close()
            raise

        if source_local:
            if t.modify_role:
                target_session.close()
                raise NotImplementedError('Modify role not implemented for '
                                          'local containers')
            if t.cleanup:
                LOG.warning('[%s] Cleanup has no effect with a local source '
                            'container.' % t.image_name)

            try:
                source_local_url = parse.urlparse(t.source_image)
                # Copy from local storage to target registry
                self._copy_local_to_registry(
                    source_local_url,
                    t.target_image_url,
                    session=target_session
                )
            except Exception:
                LOG.warning('[%s] Failed copying the target image '
                            'to the target registry' % t.target_image)
                pass
            target_session.close()
            return []

        if t.modify_role:
            image_exists = False
            try:
                image_exists = self._image_exists(t.target_image,
                                                  target_session)
            except Exception:
                LOG.warning('[%s] Failed to check if the target '
                            'image exists' % t.target_image)
                pass
            if image_exists:
                LOG.warning('[%s] Skipping upload for modified image %s' %
                            (t.image_name, t.target_image))
                target_session.close()
                return []
            copy_target_url = t.target_image_source_tag_url
        else:
            copy_target_url = t.target_image_url
        # Keep the target session open yet

        source_username, source_password = self.credentials_for_registry(
            t.source_image_url.netloc)
        try:
            source_session = self.authenticate(
                t.source_image_url,
                username=source_username,
                password=source_password
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ImageUploaderException(
                    'Unable to authenticate. This may indicate '
                    'missing registry credentials or the provided '
                    'container or namespace does not exist. %s' % e)
            raise

        source_layers = []
        manifests_str = []
        try:
            self._collect_manifests_layers(
                t.source_image_url, source_session,
                manifests_str, source_layers,
                t.multi_arch
            )

            self._cross_repo_mount(
                copy_target_url, self.image_layers, source_layers,
                session=target_session)
            to_cleanup = []

            # Copy unmodified images from source to target
            self._copy_registry_to_registry(
                t.source_image_url,
                copy_target_url,
                source_manifests=manifests_str,
                source_session=source_session,
                target_session=target_session,
                source_layers=source_layers,
                multi_arch=t.multi_arch
            )
        except Exception:
            LOG.error('[%s] Failed uploading the target '
                      'image' % t.target_image)
            # Close the sessions before raising it for more of
            # retrying perhaps
            source_session.close()
            target_session.close()
            raise

        if not t.modify_role:
            LOG.info('[%s] Completed upload for image' % t.image_name)
        else:
            LOG.info('[%s] Copy ummodified image from target to local' %
                     t.image_name)
            try:
                self._copy_registry_to_local(t.target_image_source_tag_url)

                if t.cleanup in (CLEANUP_FULL, CLEANUP_PARTIAL):
                    to_cleanup.append(t.target_image_source_tag)

                self.run_modify_playbook(
                    t.modify_role,
                    t.modify_vars,
                    t.target_image_source_tag,
                    t.target_image_source_tag,
                    t.append_tag,
                    container_build_tool='buildah')
                if t.cleanup == CLEANUP_FULL:
                    to_cleanup.append(t.target_image)

                # cross-repo mount the unmodified image to the modified image
                self._cross_repo_mount(
                    t.target_image_url, self.image_layers, source_layers,
                    session=target_session)

                # Copy from local storage to target registry
                self._copy_local_to_registry(
                    target_image_local_url,
                    t.target_image_url,
                    session=target_session
                )
                LOG.info('[%s] Completed modify and upload for image' %
                         t.image_name)
            except Exception:
                LOG.error('[%s] Failed processing the target '
                          'image' % t.target_image)
                # Close the sessions before raising it for more of
                # retrying perhaps
                source_session.close()
                target_session.close()
                raise

        try:
            for layer in source_layers:
                self.image_layers.setdefault(layer, t.target_image_url)
        except Exception:
            LOG.warning('[%s] Failed setting default layer %s for the '
                        'target image' % (t.target_image, layer))
            pass
        target_session.close()
        source_session.close()
        return to_cleanup

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _detect_target_export(cls, image_url, session):
        if image_url.netloc in cls.export_registries:
            return True
        if image_url.netloc in cls.push_registries:
            return False

        # detect if the registry is push-capable by requesting an upload URL.
        image, _ = cls._image_tag_from_url(image_url)
        upload_req_url = cls._build_url(
            image_url,
            path=CALL_UPLOAD % {'image': image})
        try:
            RegistrySessionHelper.post(
                session,
                upload_req_url,
                timeout=30
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (501, 403, 404, 405):
                cls.export_registries.add(image_url.netloc)
                return True
            else:
                raise
        cls.push_registries.add(image_url.netloc)
        return False

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _fetch_manifest(cls, url, session, multi_arch):
        image, tag = cls._image_tag_from_url(url)
        parts = {
            'image': image,
            'tag': tag
        }
        url = cls._build_url(
            url, CALL_MANIFEST % parts
        )
        if multi_arch:
            manifest_headers = {'Accept': MEDIA_MANIFEST_V2_LIST}
        else:
            manifest_headers = {'Accept': MEDIA_MANIFEST_V2}
        try:
            r = RegistrySessionHelper.get(
                session,
                url,
                headers=manifest_headers,
                timeout=30
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (403, 404):
                raise ImageNotFoundException('Not found image: %s' % url)
            else:
                raise
        return cls._get_response_text(r)

    def _collect_manifests_layers(self, image_url, session,
                                  manifests_str, layers,
                                  multi_arch):
        manifest_str = self._fetch_manifest(
            image_url,
            session=session,
            multi_arch=multi_arch
        )
        manifests_str.append(manifest_str)
        manifest = json.loads(manifest_str)
        if manifest.get('schemaVersion', 2) == 1:
            layers.extend(reversed([x['blobSum']
                                    for x in manifest['fsLayers']]))
        elif manifest.get('mediaType') == MEDIA_MANIFEST_V2:
            layers.extend(x['digest'] for x in manifest['layers'])
        elif manifest.get('mediaType') == MEDIA_MANIFEST_V2_LIST:
            image, _, tag = image_url.geturl().rpartition(':')
            for man in manifest.get('manifests', []):
                # replace image tag with the manifest hash in the list
                man_url = parse.urlparse('%s@%s' % (image, man['digest']))
                self._collect_manifests_layers(
                    man_url, session, manifests_str, layers,
                    multi_arch=False
                )

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _upload_url(cls, image_url, session, previous_request=None):
        if previous_request and 'Location' in previous_request.headers:
            return previous_request.headers['Location']

        image, tag = cls._image_tag_from_url(image_url)
        upload_req_url = cls._build_url(
            image_url,
            path=CALL_UPLOAD % {'image': image})
        r = RegistrySessionHelper.post(
            session,
            upload_req_url,
            timeout=30
        )
        return r.headers['Location']

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with longer time
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            (requests.exceptions.RequestException,
             ImageRateLimitedException)
        ),
        wait=tenacity.wait_random_exponential(multiplier=1.5, max=60),
        stop=tenacity.stop_after_attempt(5)
    )
    def _layer_stream_registry(cls, digest, source_url, calc_digest,
                               session):
        image, tag = cls._image_tag_from_url(source_url)
        parts = {
            'image': image,
            'tag': tag,
            'digest': digest
        }
        source_blob_url = cls._build_url(
            source_url, CALL_BLOB % parts)
        # NOTE(aschultz): We specify None and let requests figure it out
        chunk_size = None
        LOG.info("[%s] Fetching layer %s from %s" %
                 (image, digest, source_blob_url))
        with session.get(source_blob_url,
                         stream=True,
                         timeout=30,
                         allow_redirects=False) as blob_req:
            blob_req.encoding = 'utf-8'
            # raise for status here to ensure we didn't got a 401
            RegistrySessionHelper.check_status(session=session,
                                               request=blob_req)
            # Requests to docker.io redirect to CDN for the actual content
            # so we need to check if our initial blob request is a redirect
            # and follow as necessary.
            blob_req = RegistrySessionHelper.check_redirect_trusted(blob_req,
                                                                    session)
            for data in blob_req.iter_content(chunk_size):
                LOG.debug("[%s] Read %i bytes for %s" %
                          (image, len(data), digest))
                if not data:
                    break
                calc_digest.update(data)
                yield data
        LOG.info("[%s] Done fetching layer %s from registry" % (image, digest))

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            IOError
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _copy_layer_registry_to_registry(cls, source_url, target_url,
                                         layer,
                                         source_session=None,
                                         target_session=None):
        layer_entry = {'digest': layer}
        try:
            cls._layer_fetch_lock(layer)
            if cls._target_layer_exists_registry(
                    target_url, layer_entry, [layer_entry], target_session):
                cls._layer_fetch_unlock(layer)
                return
            known_path, ref_image = image_utils.uploaded_layers_details(
                cls._global_view_proxy(), layer, scope='local')
            if known_path and ref_image:
                # cross-link target from local source, skip fetching it again
                image_export.layer_cross_link(
                    layer, ref_image, known_path, target_url)
                cls._layer_fetch_unlock(layer)
                return
        except ImageUploaderThreadException:
            # skip trying to unlock, because that's what threw the exception
            raise
        except Exception:
            cls._layer_fetch_unlock(layer)
            raise

        digest = layer_entry['digest']
        LOG.debug('[%s] Uploading layer' % digest)

        calc_digest = hashlib.sha256()
        known_path = None
        layer_val = None
        try:
            layer_stream = cls._layer_stream_registry(
                digest, source_url, calc_digest, source_session)
            layer_val, known_path = cls._copy_stream_to_registry(
                target_url, layer_entry, calc_digest, layer_stream,
                target_session)
        except (IOError, requests.exceptions.HTTPError):
            cls._track_uploaded_layers(layer, forget=True, scope='remote')
            LOG.error('[%s] Failed processing layer for the target '
                      'image %s' % (layer, target_url.geturl()))
            raise
        except Exception:
            raise
        else:
            if layer_val and known_path:
                image_ref = target_url.path.split(':')[0][1:]
                uploaded = parse.urlparse(known_path).scheme
                cls._track_uploaded_layers(
                    layer_val, known_path=known_path, image_ref=image_ref,
                    scope=('remote' if uploaded else 'local'))
            return layer_val
        finally:
            cls._layer_fetch_unlock(layer)

    @classmethod
    def _assert_scheme(cls, url, scheme):
        if url.scheme != scheme:
            raise ImageUploaderException(
                'Expected %s scheme: %s' % (scheme, url.geturl()))

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _copy_registry_to_registry(cls, source_url, target_url,
                                   source_manifests,
                                   source_session=None,
                                   target_session=None,
                                   source_layers=None,
                                   multi_arch=False):
        cls._assert_scheme(source_url, 'docker')
        cls._assert_scheme(target_url, 'docker')

        image, tag = cls._image_tag_from_url(source_url)
        parts = {
            'image': image,
            'tag': tag
        }

        # Upload all layers
        copy_jobs = []
        jobs_count = 0
        jobs_finished = 0
        with futures.ThreadPoolExecutor(max_workers=4) as p:
            if source_layers:
                for layer in source_layers:
                    copy_jobs.append(p.submit(
                        cls._copy_layer_registry_to_registry,
                        source_url, target_url,
                        layer=layer,
                        source_session=source_session,
                        target_session=target_session
                    ))

            jobs_count = len(copy_jobs)
            LOG.debug('[%s] Waiting for %i jobs to finish' %
                      (image, jobs_count))
            for job in futures.as_completed(copy_jobs):
                e = job.exception()
                if e:
                    raise e
                layer = job.result()
                if layer:
                    LOG.debug('[%s] Upload complete for layer %s' %
                              (image, layer))
                jobs_finished += 1
                LOG.debug('[%s] Waiting for next job: %i of %i complete' %
                          (image, jobs_finished, jobs_count))

        LOG.debug('[%s] Completed %i jobs' % (image, jobs_count))

        for source_manifest in source_manifests:
            manifest = json.loads(source_manifest)
            config_str = None
            if manifest.get('mediaType') == MEDIA_MANIFEST_V2:
                config_digest = manifest['config']['digest']
                LOG.debug('[%s] Uploading config with digest: %s' %
                          (image, config_digest))

                parts['digest'] = config_digest
                source_config_url = cls._build_url(
                    source_url,
                    CALL_BLOB % parts
                )

                r = RegistrySessionHelper.get(
                    source_session,
                    source_config_url,
                    timeout=30,
                    allow_redirects=False
                )
                # check if the blob was a redirect
                r = RegistrySessionHelper.check_redirect_trusted(
                    r, source_session, stream=False)

                config_str = cls._get_response_text(r)
                manifest['config']['size'] = len(config_str)
                manifest['config']['mediaType'] = MEDIA_CONFIG

            cls._copy_manifest_config_to_registry(
                target_url=target_url,
                manifest_str=source_manifest,
                config_str=config_str,
                target_session=target_session,
                multi_arch=multi_arch
            )
        LOG.debug('[%s] Finished copying image' % image)

    @classmethod
    def _copy_manifest_config_to_registry(cls, target_url,
                                          manifest_str,
                                          config_str,
                                          target_session=None,
                                          multi_arch=False):

        manifest = json.loads(manifest_str)
        if manifest.get('schemaVersion', 2) == 1:
            if 'signatures' in manifest:
                manifest_type = MEDIA_MANIFEST_V1_SIGNED
            else:
                manifest_type = MEDIA_MANIFEST_V1
        else:
            # NOTE(mwhahaha): always force docker media format if not set or
            # is explicitly OCI because buildah uses OCI by default but we
            # convert the metadata to Docker format in the uploader.
            # See LP#1860585
            manifest_type = manifest.get('mediaType', False)
            if not manifest_type or manifest_type == MEDIA_OCI_MANIFEST_V1:
                manifest_type = MEDIA_MANIFEST_V2
            elif manifest_type == MEDIA_OCI_INDEX_V1:
                manifest_type = MEDIA_MANIFEST_V2_LIST
            manifest['mediaType'] = manifest_type
            manifest_str = json.dumps(manifest, indent=3)

        export = target_url.netloc in cls.export_registries
        if export:
            image_export.export_manifest_config(
                target_url,
                manifest_str,
                manifest_type,
                config_str,
                multi_arch=multi_arch
            )
            return

        if config_str is not None:
            config_digest = manifest['config']['digest']
            # Upload the config json as a blob
            upload_url = cls._upload_url(
                target_url,
                session=target_session)
            r = RegistrySessionHelper.put(
                target_session,
                upload_url,
                timeout=30,
                params={
                    'digest': config_digest
                },
                data=config_str.encode('utf-8'),
                headers={
                    'Content-Length': str(len(config_str)),
                    'Content-Type': 'application/octet-stream'
                }
            )

        # Upload the manifest
        image, tag = cls._image_tag_from_url(target_url)
        parts = {
            'image': image,
            'tag': tag
        }
        manifest_url = cls._build_url(
            target_url, CALL_MANIFEST % parts)

        LOG.debug('[%s] Uploading manifest of type %s to: %s' %
                  (image, manifest_type, manifest_url))

        try:
            r = RegistrySessionHelper.put(
                target_session,
                manifest_url,
                timeout=30,
                data=manifest_str.encode('utf-8'),
                headers={
                    'Content-Type': manifest_type
                }
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                LOG.error(cls._get_response_text(r))
                raise ImageUploaderException('Pushing manifest failed')
            else:
                raise

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _copy_registry_to_local(cls, source_url):
        cls._assert_scheme(source_url, 'docker')
        pull_source = source_url.netloc + source_url.path
        cmd = ['buildah', '--debug', 'pull']

        if source_url.netloc in [cls.insecure_registries,
                                 cls.no_verify_registries]:
            cmd.append('--tls-verify=false')

        cmd.append(pull_source)
        LOG.info('Pulling %s' % pull_source)
        LOG.info('Running %s' % ' '.join(cmd))
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                close_fds=True
            )
            out, err = process.communicate()
            if process.returncode != 0:
                error_msg = (
                    'Pulling image failed: cmd "{}", stdout "{}",'
                    ' stderr "{}"'.format(
                        ' '.join(cmd),
                        out,
                        err
                    )
                )
                LOG.error(error_msg)
                raise ImageUploaderException(error_msg)
        except KeyboardInterrupt:
            raise Exception('Action interrupted with ctrl+c')
        return out

    @classmethod
    def _target_layer_exists_registry(cls, target_url, layer, check_layers,
                                      session):
        image, tag = cls._image_tag_from_url(target_url)
        norm_image = (image[1:] if image.startswith('/') else image)
        parts = {
            'image': image,
            'tag': tag
        }
        layer_found = None
        # Check in global view or do a HEAD call for the supplied
        # digests to see if the layer is already in the registry
        for x in check_layers:
            if not x:
                continue
            known_path, ref_image = image_utils.uploaded_layers_details(
                cls._global_view_proxy(), x['digest'], scope='remote')
            if ref_image == norm_image:
                LOG.debug('[%s] Layer %s already exists at %s' %
                          (image, x['digest'], known_path))
                layer_found = x
                break
            else:
                parts['digest'] = x['digest']
                blob_url = cls._build_url(
                    target_url, CALL_BLOB % parts)
                if session.head(blob_url, timeout=30).status_code == 200:
                    LOG.debug('[%s] Layer already exists: %s' %
                              (image, x['digest']))
                    layer_found = x
                    break
        if layer_found:
            layer['digest'] = layer_found['digest']
            if 'size' in layer_found:
                layer['size'] = layer_found['size']
            if 'mediaType' in layer_found:
                layer['mediaType'] = layer_found['mediaType']
            return True
        return False

    @classmethod
    def _layer_stream_local(cls, layer_id, calc_digest):
        LOG.debug('[%s] Exporting layer' % layer_id)

        tar_split_path = cls._containers_file_path(
            'overlay-layers',
            '%s.tar-split.gz' % layer_id
        )
        overlay_path = cls._containers_file_path(
            'overlay', layer_id, 'diff'
        )
        cmd = [
            'tar-split', 'asm',
            '--input', tar_split_path,
            '--path', overlay_path,
            '--compress'
        ]
        LOG.debug(' '.join(cmd))
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE)

            chunk_size = 2 ** 20

            while True:
                data = p.stdout.read(chunk_size)
                if not data:
                    break
                calc_digest.update(data)
                yield data
            p.wait()
            if p.returncode != 0:
                raise ImageUploaderException('Extracting layer failed')
        except KeyboardInterrupt:
            raise Exception('Action interrupted with ctrl+c')

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _copy_layer_local_to_registry(cls, target_url,
                                      session, layer, layer_entry):

        # Check in global view or do a HEAD call for the compressed-diff-digest
        # and diff-digest to see if the layer is already in the registry
        check_layers = []
        compressed_digest = layer_entry.get('compressed-diff-digest')
        if compressed_digest:
            check_layers.append({
                'digest': compressed_digest,
                'size': layer_entry.get('compressed-size'),
                'mediaType': MEDIA_BLOB_COMPRESSED,
            })

        digest = layer_entry.get('diff-digest')
        if digest:
            check_layers.append({
                'digest': digest,
                'size': layer_entry.get('diff-size'),
                'mediaType': MEDIA_BLOB,
            })
        if cls._target_layer_exists_registry(target_url, layer, check_layers,
                                             session):
            return

        layer_id = layer_entry['id']
        LOG.debug('[%s] Uploading layer' % layer_id)

        calc_digest = hashlib.sha256()
        known_path = None
        layer_val = None
        try:
            layer_stream = cls._layer_stream_local(layer_id, calc_digest)
            layer_val, known_path = cls._copy_stream_to_registry(
                target_url, layer, calc_digest, layer_stream, session,
                verify_digest=False)
        except (IOError, requests.exceptions.HTTPError):
            cls._track_uploaded_layers(
                layer['digest'], forget=True, scope='remote')
            LOG.error('[%s] Failed processing layer for the target '
                      'image %s' % (layer['digest'], target_url.geturl()))
            raise
        except Exception:
            raise
        else:
            if layer_val and known_path:
                image_ref = target_url.path.split(':')[0][1:]
                uploaded = parse.urlparse(known_path).scheme
                cls._track_uploaded_layers(
                    layer_val, known_path=known_path, image_ref=image_ref,
                    scope=('remote' if uploaded else 'local'))
            return layer_val

    @classmethod
    def _copy_stream_to_registry(cls, target_url, layer, calc_digest,
                                 layer_stream, session, verify_digest=True):
        layer['mediaType'] = MEDIA_BLOB_COMPRESSED
        length = 0
        upload_resp = None

        export = target_url.netloc in cls.export_registries
        if export:
            return image_export.export_stream(
                target_url, layer, layer_stream, verify_digest=verify_digest)

        for chunk in layer_stream:
            if not chunk:
                break

            chunk_length = len(chunk)
            upload_url = cls._upload_url(
                target_url, session, upload_resp)
            upload_resp = RegistrySessionHelper.patch(
                session,
                upload_url,
                timeout=30,
                data=chunk,
                headers={
                    'Content-Length': str(chunk_length),
                    'Content-Range': '%d-%d' % (
                        length, length + chunk_length - 1),
                    'Content-Type': 'application/octet-stream'
                }
            )
            length += chunk_length

        layer_digest = 'sha256:%s' % calc_digest.hexdigest()
        LOG.debug('[%s] Calculated layer digest' % layer_digest)
        upload_url = cls._upload_url(
            target_url, session, upload_resp)
        upload_resp = RegistrySessionHelper.put(
            session,
            upload_url,
            timeout=30,
            params={
                'digest': layer_digest
            },
        )
        layer['digest'] = layer_digest
        layer['size'] = length
        return (layer_digest, cls._build_url(target_url, target_url.path))

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _copy_local_to_registry(cls, source_url, target_url, session):
        cls._assert_scheme(source_url, 'containers-storage')
        cls._assert_scheme(target_url, 'docker')

        name = '%s%s' % (source_url.netloc, source_url.path)
        image, manifest, config_str = cls._image_manifest_config(name)
        layers_by_digest = cls._get_all_local_layers_by_digest()

        # Upload all layers
        copy_jobs = []
        jobs_count = 0
        jobs_finished = 0
        with futures.ThreadPoolExecutor(max_workers=4) as p:
            for layer in manifest['layers']:
                layer_entry = layers_by_digest[layer['digest']]
                copy_jobs.append(p.submit(
                    cls._copy_layer_local_to_registry,
                    target_url, session, layer, layer_entry
                ))
            jobs_count = len(copy_jobs)
            LOG.debug('[%s] Waiting for %i jobs to finish' %
                      (name, jobs_count))
            for job in futures.as_completed(copy_jobs):
                e = job.exception()
                if e:
                    raise e
                layer = job.result()
                if layer:
                    LOG.debug('[%s] Upload complete for layer: %s' %
                              (name, layer))
                jobs_finished += 1
                LOG.debug('[%s] Waiting for next job: %i of %i complete' %
                          (name, jobs_finished, jobs_count))

        LOG.debug('[%s] Completed %i jobs' % (name, jobs_count))

        manifest_str = json.dumps(manifest, indent=3)
        cls._copy_manifest_config_to_registry(
            target_url=target_url,
            manifest_str=manifest_str,
            config_str=config_str,
            target_session=session
        )
        LOG.debug('[%s] Finished copying' % name)

    @classmethod
    def _containers_file_path(cls, *path):
        full_path = os.path.join('/var/lib/containers/storage/', *path)
        if not os.path.exists(full_path):
            raise ImageUploaderException('Missing file %s' % full_path)
        return full_path

    @classmethod
    def _containers_file(cls, *path):
        full_path = cls._containers_file_path(*path)

        try:
            with open(full_path, 'r') as f:
                return f.read()
        except Exception as e:
            raise ImageUploaderException(e)

    @classmethod
    def _containers_json(cls, *path):
        return json.loads(cls._containers_file(*path))

    @classmethod
    def _get_all_local_layers_by_digest(cls):
        all_layers = cls._containers_json('overlay-layers', 'layers.json')
        layers_by_digest = {}
        for x in all_layers:
            if 'diff-digest' in x:
                layers_by_digest[x['diff-digest']] = x
            if 'compressed-diff-digest' in x:
                layers_by_digest[x['compressed-diff-digest']] = x
        return layers_by_digest

    @classmethod
    def _get_local_layers_manifest(cls, manifest, config_str):
        """Return a valid local manifest

        The manifest that is kept in the container storage is the
        original manifest but the layers may be different once processed
        by libpod & company. We want a valid manifest for the local
        file system so we need to use the root fs layers from the container
        config rather than just assuming the original manifest is still
        valid.
        """
        layers = cls._get_all_local_layers_by_digest()
        config = json.loads(config_str)
        rootfs = config.get('rootfs', {})
        layer_ids = rootfs.get('diff_ids', None)
        if not layer_ids:
            # TODO(aschultz): add container name/path
            LOG.warning('Container missing rootfs layers')
            return manifest
        # clear out the manifest layers
        manifest['layers'] = []
        for layer in layer_ids:
            layer_digest = {'mediaType': MEDIA_BLOB}
            if layer not in layers:
                raise ImageNotFoundException('Unable to find layer %s in the '
                                             'local layers' % layer)
            layer_digest['digest'] = layer
            # podman currently doesn't do compressed layers so just use
            # the diff-size
            layer_digest['size'] = layers[layer]['diff-size']
            manifest['layers'].append(layer_digest)
        return manifest

    @classmethod
    def _image_manifest_config(cls, name):
        image = None
        images = cls._containers_json('overlay-images', 'images.json')
        for i in images:
            for n in i.get('names', []):
                if name == n:
                    image = i
                    break
            if image:
                break
        if not image:
            raise ImageNotFoundException('Not found image: %s' % name)
        image_id = image['id']
        manifest = cls._containers_json('overlay-images', image_id, 'manifest')
        config_digest = manifest['config']['digest']

        config_id = '=' + base64.b64encode(
            six.b(config_digest)).decode("utf-8")
        config_str = cls._containers_file('overlay-images', image_id,
                                          config_id)
        manifest = cls._get_local_layers_manifest(manifest, config_str)
        manifest['config']['size'] = len(config_str)
        manifest['config']['mediaType'] = MEDIA_CONFIG
        return image, manifest, config_str

    @classmethod
    def _inspect(cls, image_url, session=None, default_tag=False):
        if image_url.scheme == 'docker':
            return super(PythonImageUploader, cls)._inspect(
                image_url, session=session, default_tag=default_tag)
        if image_url.scheme != 'containers-storage':
            raise ImageUploaderException('Inspect not implemented for %s' %
                                         image_url.geturl())

        name = '%s%s' % (image_url.netloc, image_url.path)
        image, manifest, config_str = cls._image_manifest_config(name)
        config = json.loads(config_str)

        layers = [x['digest'] for x in manifest['layers']]
        i, _ = cls._image_tag_from_url(image_url)
        digest = image['digest']
        created = image['created']
        labels = config['config'].get('Labels', {})
        # NOTE: labels can be null
        if labels is None:
            labels = {}
        architecture = config['architecture']
        image_os = config['os']
        return {
            'Name': i,
            'Digest': digest,
            'RepoTags': [],
            'Created': created,
            'DockerVersion': '',
            'Labels': labels,
            'Architecture': architecture,
            'Os': image_os,
            'Layers': layers,
        }

    @classmethod
    def _delete_from_registry(cls, image_url, session=None):
        if not cls._detect_target_export(image_url, session):
            raise NotImplementedError(
                'Deleting not supported via the registry API')
        return image_export.delete_image(image_url)

    @classmethod
    def _delete(cls, image_url, session=None):
        image = image_url.geturl()
        LOG.info('[%s] Deleting image' % image)
        if image_url.scheme == 'docker':
            return cls._delete_from_registry(image_url, session)
        if image_url.scheme != 'containers-storage':
            raise ImageUploaderException('Delete not implemented for %s' %
                                         image_url.geturl())
        cmd = ['buildah', 'rmi', image_url.path]
        LOG.info('Running %s' % ' '.join(cmd))
        env = os.environ.copy()
        try:
            process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                       universal_newlines=True)

            out, err = process.communicate()
            LOG.info(out)
            if process.returncode != 0:
                LOG.warning('Error deleting image:\n%s\n%s' %
                            (' '.join(cmd), err))
        except KeyboardInterrupt:
            raise Exception('Action interrupted with ctrl+c')
        return out

    def cleanup(self, local_images):
        if not local_images:
            return []

        for image in sorted(local_images):
            if not image:
                continue
            LOG.info('[%s] Removing local copy of image' % image)
            image_url = parse.urlparse('containers-storage:%s' % image)
            self._delete(image_url)

    def _get_executor(self):
        """Get executor type based on lock object

        We check to see if the lock object is not set or if it is a threading
        lock. We cannot check if it is a ProcessLock due to the side effect
        of trying to include ProcessLock when running under Mistral breaks
        Mistral.
        """
        if not self.lock or isinstance(self.lock, threadinglock.ThreadingLock):
            # workers will scale from 2 to 8 based on the cpu count // 2
            workers = min(max(2, processutils.get_worker_count() // 2), 8)
            return futures.ThreadPoolExecutor(max_workers=workers)
        else:
            # there really isn't an improvement with > 4 workers due to the
            # container layer overlaps. The higher the workers, the more
            # RAM required which can lead to OOMs. It's best to limit to 4
            return futures.ProcessPoolExecutor(max_workers=4)

    def run_tasks(self):
        if not self.upload_tasks:
            return
        local_images = []

        with self._get_executor() as p:
            for result in p.map(upload_task, self.upload_tasks):
                local_images.extend(result)
            LOG.info('result %s' % local_images)

        # Do cleanup after all the uploads so common layers don't get deleted
        # repeatedly
        self.cleanup(local_images)


class UploadTask(object):

    def __init__(self, image_name, pull_source, push_destination,
                 append_tag, modify_role, modify_vars, cleanup,
                 multi_arch):
        self.image_name = image_name
        self.pull_source = pull_source
        self.push_destination = push_destination
        self.append_tag = append_tag or ''
        self.modify_role = modify_role
        self.modify_vars = modify_vars
        self.cleanup = cleanup
        self.multi_arch = multi_arch

        if ':' in image_name:
            image = image_name.rpartition(':')[0]
            self.source_tag = image_name.rpartition(':')[2]
        else:
            image = image_name
            self.source_tag = 'latest'
        if pull_source:
            # prevent a double // in the url which causes auth problems
            # with docker.io
            if pull_source.endswith('/'):
                pull_source = pull_source[:-1]
            self.repo = pull_source + '/' + image
        else:
            self.repo = image

        if push_destination.endswith('/'):
            push_destination = push_destination[:-1]
        self.target_image_no_tag = (push_destination + '/' +
                                    self.repo.partition('/')[2])
        self.target_tag = self.source_tag + self.append_tag
        self.source_image = self.repo + ':' + self.source_tag
        self.target_image_source_tag = (self.target_image_no_tag + ':' +
                                        self.source_tag)
        self.target_image = self.target_image_no_tag + ':' + self.target_tag

        image_to_url = BaseImageUploader._image_to_url
        self.source_image_url = image_to_url(self.source_image)
        self.target_image_url = image_to_url(self.target_image)
        self.target_image_source_tag_url = image_to_url(
            self.target_image_source_tag
        )


def upload_task(args):
    uploader, task = args
    return uploader.upload_image(task)


def discover_tag_from_inspect(args):
    self, image, tag_from_label, default_tag = args
    image_url = self._image_to_url(image)
    username, password = self.credentials_for_registry(image_url.netloc)
    try:
        session = self.authenticate(
            image_url, username=username, password=password)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            raise ImageUploaderException(
                'Unable to authenticate. This may indicate '
                'missing registry credentials or the provided '
                'container or namespace does not exist. %s' % e)
        raise
    i = self._inspect(image_url, session=session, default_tag=default_tag)
    session.close()
    if ':' in image_url.path:
        # break out the tag from the url to be the fallback tag
        path = image.rpartition(':')
        fallback_tag = path[2]
        image = path[0]
    else:
        fallback_tag = None
    return image, self._discover_tag_from_inspect(
        i, image, tag_from_label, fallback_tag)


def tags_for_image(args):
    self, image, session = args
    return self._tags_for_image(image, session)
