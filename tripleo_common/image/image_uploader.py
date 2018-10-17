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


import abc
from concurrent import futures
import json
import netifaces
import os
import re
import requests
from requests import auth as requests_auth
import shutil
import six
from six.moves.urllib import parse
import subprocess
import tempfile
import tenacity
import yaml

import docker
try:
    from docker import APIClient as Client
except ImportError:
    from docker import Client
from oslo_concurrency import processutils
from oslo_log import log as logging
from tripleo_common.actions import ansible
from tripleo_common.image.base import BaseImageManager
from tripleo_common.image.exception import ImageNotFoundException
from tripleo_common.image.exception import ImageUploaderException


LOG = logging.getLogger(__name__)


SECURE_REGISTRIES = (
    'trunk.registry.rdoproject.org',
    'docker.io',
    'registry-1.docker.io',
)

CLEANUP = (
    CLEANUP_FULL, CLEANUP_PARTIAL, CLEANUP_NONE
) = (
    'full', 'partial', 'none'
)


DEFAULT_UPLOADER = 'docker'


def get_undercloud_registry():
    addr = 'localhost'
    if 'br-ctlplane' in netifaces.interfaces():
        addrs = netifaces.ifaddresses('br-ctlplane')
        if netifaces.AF_INET in addrs and addrs[netifaces.AF_INET]:
            addr = addrs[netifaces.AF_INET][0].get('addr', 'localhost')
    return '%s:%s' % (addr, '8787')


class ImageUploadManager(BaseImageManager):
    """Manage the uploading of image files

       Manage the uploading of images from a config file specified in YAML
       syntax. Multiple config files can be specified. They will be merged.
       """

    def __init__(self, config_files=None, verbose=False, debug=False,
                 dry_run=False, cleanup=CLEANUP_FULL):
        if config_files is None:
            config_files = []
        super(ImageUploadManager, self).__init__(config_files)
        self.uploaders = {}
        self.dry_run = dry_run
        self.cleanup = cleanup

    def discover_image_tag(self, image, tag_from_label=None,
                           username=None, password=None):
        uploader = self.uploader(DEFAULT_UPLOADER)
        return uploader.discover_image_tag(
            image, tag_from_label=tag_from_label,
            username=username, password=password)

    def uploader(self, uploader):
        if uploader not in self.uploaders:
            self.uploaders[uploader] = ImageUploader.get_uploader(uploader)
        return self.uploaders[uploader]

    def get_push_destination(self, item):
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

            self.uploader(uploader).add_upload_task(
                image_name, pull_source, push_destination,
                append_tag, modify_role, modify_vars, self.dry_run,
                self.cleanup)

        for uploader in self.uploaders.values():
            uploader.run_tasks()

        return upload_images  # simply to make test validation easier


@six.add_metaclass(abc.ABCMeta)
class ImageUploader(object):
    """Base representation of an image uploading method"""

    @staticmethod
    def get_uploader(uploader):
        if uploader == 'docker':
            return DockerImageUploader()
        if uploader == 'skopeo':
            return SkopeoImageUploader()
        raise ImageUploaderException('Unknown image uploader type')

    @abc.abstractmethod
    def run_tasks(self):
        """Run all tasks"""
        pass

    @abc.abstractmethod
    def add_upload_task(self, image_name, pull_source, push_destination,
                        append_tag, modify_role, modify_vars, dry_run,
                        cleanup):
        """Add an upload task to be executed later"""
        pass

    @abc.abstractmethod
    def discover_image_tag(self, image, tag_from_label=None,
                           username=None, password=None):
        """Discover a versioned tag for an image"""
        pass

    @abc.abstractmethod
    def cleanup(self):
        """Remove unused images or temporary files from upload"""
        pass

    @abc.abstractmethod
    def is_insecure_registry(self, registry_host):
        """Detect whether a registry host is not configured with TLS"""
        pass


class BaseImageUploader(ImageUploader):

    def __init__(self):
        self.upload_tasks = []
        self.secure_registries = set(SECURE_REGISTRIES)
        self.insecure_registries = set()
        # A mapping of layer hashs to the image which first copied that
        # layer to the target
        self.image_layers = {}

    def cleanup(self):
        pass

    def run_tasks(self):
        pass

    @staticmethod
    def source_target_names(image_name, pull_source, push_destination,
                            append_tag):
        if ':' in image_name:
            image = image_name.rpartition(':')[0]
            source_tag = image_name.rpartition(':')[2]
        else:
            image = image_name
            source_tag = 'latest'
        if pull_source:
            repo = pull_source + '/' + image
        else:
            repo = image

        target_image_no_tag = push_destination + '/' + repo.partition('/')[2]
        append_tag = append_tag or ''
        target_tag = source_tag + append_tag
        return {
            'repo': repo,
            'source_tag': source_tag,
            'source_image': repo + ':' + source_tag,
            'target_image_no_tag': target_image_no_tag,
            'append_tag': append_tag,
            'target_tag': target_tag,
            'target_image_source_tag': target_image_no_tag + ':' + source_tag,
            'target_image': target_image_no_tag + ':' + target_tag,
        }

    @staticmethod
    def run_modify_playbook(modify_role, modify_vars,
                            source_image, target_image, append_tag,
                            container_build_tool='docker'):
        vars = {}
        if modify_vars:
            vars.update(modify_vars)
        vars['source_image'] = source_image
        vars['target_image'] = target_image
        vars['modified_append_tag'] = append_tag
        vars['container_build_tool'] = container_build_tool
        LOG.info('Playbook variables: \n%s' % yaml.safe_dump(
            vars, default_flow_style=False))
        playbook = [{
            'hosts': 'localhost',
            'tasks': [{
                'name': 'Import role %s' % modify_role,
                'import_role': {
                    'name': modify_role
                },
                'vars': vars
            }]
        }]
        LOG.info('Playbook: \n%s' % yaml.safe_dump(
            playbook, default_flow_style=False))
        work_dir = tempfile.mkdtemp(prefix='tripleo-modify-image-playbook-')
        try:
            action = ansible.AnsiblePlaybookAction(
                playbook=playbook,
                work_dir=work_dir,
                verbosity=3,
                extra_env_variables=dict(os.environ)
            )
            result = action.run(None)
            log_path = result.get('log_path')
            if log_path and os.path.isfile(log_path):
                with open(log_path) as f:
                    LOG.info(f.read())
            shutil.rmtree(work_dir)
        except processutils.ProcessExecutionError as e:
            LOG.error('%s\nError running playbook in directory: %s'
                      % (e.stdout, work_dir))
            raise ImageUploaderException(
                'Modifying image %s failed' % target_image)

    @staticmethod
    def _images_match(image1, image2, insecure_registries, session1=None):
        try:
            image1_digest = BaseImageUploader._image_digest(
                image1, insecure_registries, session=session1)
        except Exception:
            return False
        try:
            image2_digest = BaseImageUploader._image_digest(
                image2, insecure_registries)
        except Exception:
            return False

        # missing digest, no way to know if they match
        if not image1_digest or not image2_digest:
            return False
        return image1_digest == image2_digest

    @staticmethod
    def _image_digest(image, insecure_registries, session=None):
        image_url = BaseImageUploader._image_to_url(image)
        insecure = image_url.netloc in insecure_registries
        i = BaseImageUploader._inspect(image_url, insecure, session)
        return i.get('Digest')

    @staticmethod
    def _image_labels(image_url, insecure, session=None):
        i = BaseImageUploader._inspect(image_url, insecure, session)
        return i.get('Labels', {}) or {}

    @staticmethod
    def _image_exists(image, insecure_registries, session=None):
        try:
            BaseImageUploader._image_digest(
                image, insecure_registries, session=session)
        except ImageNotFoundException:
            return False
        else:
            return True

    @staticmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def authenticate(image_url, username=None, password=None, insecure=False):
        image_url = BaseImageUploader._fix_dockerio_url(image_url)
        netloc = image_url.netloc
        if insecure:
            scheme = 'http'
        else:
            scheme = 'https'
        image, tag = image_url.path.split(':')
        url = '%s://%s/v2/' % (scheme, netloc)
        session = requests.Session()
        r = session.get(url, timeout=30)
        LOG.debug('%s status code %s' % (url, r.status_code))
        if r.status_code == 200:
            return session
        if r.status_code != 401:
            r.raise_for_status()
        if 'www-authenticate' not in r.headers:
            raise ImageUploaderException(
                'Unknown authentication method for headers: %s' % r.headers)

        www_auth = r.headers['www-authenticate']
        if not www_auth.startswith('Bearer '):
            raise ImageUploaderException(
                'Unknown www-authenticate value: %s' % www_auth)
        token_param = {}

        realm = re.search('realm="(.*?)"', www_auth).group(1)
        if 'service=' in www_auth:
            token_param['service'] = re.search(
                'service="(.*?)"', www_auth).group(1)
        token_param['scope'] = 'repository:%s:pull' % image[1:]
        auth = None
        if username:
            auth = requests_auth.HTTPBasicAuth(username, password)
        rauth = session.get(realm, params=token_param, auth=auth, timeout=30)
        rauth.raise_for_status()
        session.headers['Authorization'] = 'Bearer %s' % rauth.json()['token']
        return session

    @staticmethod
    def _fix_dockerio_url(url):
        one = 'docker.io'
        two = 'registry-1.docker.io'
        if url.netloc != one:
            return url
        return parse.ParseResult(url.scheme, two,
                                 url.path, url.params,
                                 url.query, url.fragment)

    @staticmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _inspect(image_url, insecure=False, session=None):
        original_image_url = image_url
        image_url = BaseImageUploader._fix_dockerio_url(image_url)
        parts = {
            'netloc': image_url.netloc
        }
        if insecure:
            parts['scheme'] = 'http'
        else:
            parts['scheme'] = 'https'
        image, tag = image_url.path.split(':')
        parts['image'] = image
        parts['tag'] = tag

        manifest_url = ('%(scheme)s://%(netloc)s/v2'
                        '%(image)s/manifests/%(tag)s' % parts)
        tags_url = ('%(scheme)s://%(netloc)s/v2'
                    '%(image)s/tags/list' % parts)
        manifest_headers = {
            'Accept': 'application/vnd.docker.distribution.manifest.v2+json'
        }

        p = futures.ThreadPoolExecutor(max_workers=2)
        manifest_f = p.submit(
            session.get, manifest_url, headers=manifest_headers, timeout=30)
        tags_f = p.submit(session.get, tags_url, timeout=30)

        manifest_r = manifest_f.result()
        tags_r = tags_f.result()

        if manifest_r.status_code == 404:
            raise ImageNotFoundException('Not found image: %s' %
                                         image_url.geturl())
        manifest_r.raise_for_status()
        tags_r.raise_for_status()

        manifest = manifest_r.json()
        layers = [l['digest'] for l in manifest['layers']]

        parts['config_digest'] = manifest['config']['digest']
        config_headers = {
            'Accept': manifest['config']['mediaType']
        }
        config_url = ('%(scheme)s://%(netloc)s/v2'
                      '%(image)s/blobs/%(config_digest)s' % parts)
        config_f = p.submit(
            session.get, config_url, headers=config_headers, timeout=30)
        config_r = config_f.result()
        config_r.raise_for_status()

        tags = tags_r.json()['tags']
        digest = manifest_r.headers['Docker-Content-Digest']
        config = config_r.json()
        name = '%s%s' % (original_image_url.netloc, image)

        return {
            'Name': name,
            'Digest': digest,
            'RepoTags': tags,
            'Created': config['created'],
            'DockerVersion': config['docker_version'],
            'Labels': config['config']['Labels'],
            'Architecture': config['architecture'],
            'Os': config['os'],
            'Layers': layers,
        }

    @staticmethod
    def _image_to_url(image):
        if '://' not in image:
            image = 'docker://' + image
        url = parse.urlparse(image)
        return url

    @staticmethod
    def _discover_tag_from_inspect(i, image, tag_from_label=None,
                                   fallback_tag=None):
        labels = i.get('Labels', {})

        label_keys = ', '.join(labels.keys())

        if not tag_from_label:
            raise ImageUploaderException(
                'No label specified. Available labels: %s' % label_keys
            )

        if "{" in tag_from_label:
            try:
                tag_label = tag_from_label.format(**labels)
            except ValueError as e:
                raise ImageUploaderException(e)
            except KeyError as e:
                if fallback_tag:
                    tag_label = fallback_tag
                else:
                    raise ImageUploaderException(
                        'Image %s %s. Available labels: %s' %
                        (image, e, label_keys)
                    )
        else:
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

    def discover_image_tags(self, images, tag_from_label=None):
        image_urls = [self._image_to_url(i) for i in images]

        # prime self.insecure_registries by testing every image
        for url in image_urls:
            self.is_insecure_registry(url.netloc)

        discover_args = []
        for image in images:
            discover_args.append((image, tag_from_label,
                                  self.insecure_registries))
        p = futures.ThreadPoolExecutor(max_workers=16)

        versioned_images = {}
        for image, versioned_image in p.map(discover_tag_from_inspect,
                                            discover_args):
            versioned_images[image] = versioned_image
        return versioned_images

    def discover_image_tag(self, image, tag_from_label=None,
                           fallback_tag=None, username=None, password=None):
        image_url = self._image_to_url(image)
        insecure = self.is_insecure_registry(image_url.netloc)
        session = self.authenticate(
            image_url, insecure=insecure, username=username, password=password)
        i = self._inspect(image_url, insecure, session)
        return self._discover_tag_from_inspect(i, image, tag_from_label,
                                               fallback_tag)

    def filter_images_with_labels(self, images, labels,
                                  username=None, password=None):
        images_with_labels = []
        for image in images:
            url = self._image_to_url(image)
            insecure = self.is_insecure_registry(url.netloc)
            session = self.authenticate(
                url, insecure=insecure, username=username, password=password)
            image_labels = self._image_labels(
                url, insecure=insecure, session=session)
            if set(labels).issubset(set(image_labels)):
                images_with_labels.append(image)

        return images_with_labels

    def add_upload_task(self, image_name, pull_source, push_destination,
                        append_tag, modify_role, modify_vars, dry_run,
                        cleanup):
        # prime self.insecure_registries
        if pull_source:
            self.is_insecure_registry(self._image_to_url(pull_source).netloc)
        else:
            self.is_insecure_registry(self._image_to_url(image_name).netloc)
        self.is_insecure_registry(self._image_to_url(push_destination).netloc)
        self.upload_tasks.append((image_name, pull_source, push_destination,
                                  self.insecure_registries, append_tag,
                                  modify_role, modify_vars, dry_run, cleanup,
                                  self.image_layers))

    def is_insecure_registry(self, registry_host):
        if registry_host in self.secure_registries:
            return False
        if registry_host in self.insecure_registries:
            return True
        try:
            requests.get('https://%s/' % registry_host)
        except requests.exceptions.SSLError:
            self.insecure_registries.add(registry_host)
            return True
        except Exception:
            # for any other error assume it is a secure registry, because:
            # - it is secure registry
            # - the host is not accessible
            pass
        self.secure_registries.add(registry_host)
        return False

    @staticmethod
    def _cross_repo_mount(target_image_url, image_layers,
                          source_layers, insecure_registries, session):
        netloc = target_image_url.netloc
        name = target_image_url.path.split(':')[0][1:]
        if netloc in insecure_registries:
            scheme = 'http'
        else:
            scheme = 'https'
        url = '%s://%s/v2/%s/blobs/uploads/' % (scheme, netloc, name)

        for layer in source_layers:
            if layer in image_layers:
                existing_name = image_layers[layer].path.split(':')[0][1:]
                LOG.info('Cross repository blob mount %s from %s' %
                         (layer, existing_name))
                data = {
                    'mount': layer,
                    'from': existing_name
                }
                r = session.post(url, data=data)
                LOG.debug('%s %s' % (r.status_code, r.reason))


class DockerImageUploader(BaseImageUploader):
    """Upload images using docker pull/tag/push"""

    @staticmethod
    def upload_image(image_name, pull_source, push_destination,
                     insecure_registries, append_tag, modify_role,
                     modify_vars, dry_run, cleanup, image_layers):
        LOG.info('imagename: %s' % image_name)
        names = BaseImageUploader.source_target_names(
            image_name, pull_source, push_destination, append_tag)
        source_tag = names['source_tag']
        repo = names['repo']
        source_image = names['source_image']
        source_image_url = BaseImageUploader._image_to_url(source_image)
        source_insecure = source_image_url.netloc in insecure_registries
        target_image_no_tag = names['target_image_no_tag']
        append_tag = names['append_tag']
        target_tag = names['target_tag']
        target_image_source_tag = names['target_image_source_tag']
        target_image = names['target_image']
        target_image_url = BaseImageUploader._image_to_url(target_image)
        target_insecure = target_image_url.netloc in insecure_registries

        if dry_run:
            return []

        if modify_role:
            target_session = BaseImageUploader.authenticate(
                target_image_url, insecure=target_insecure)
            if BaseImageUploader._image_exists(target_image,
                                               insecure_registries,
                                               session=target_session):
                LOG.warning('Skipping upload for modified image %s' %
                            target_image)
                return []
        else:
            source_session = BaseImageUploader.authenticate(
                source_image_url, insecure=source_insecure)
            if BaseImageUploader._images_match(source_image, target_image,
                                               insecure_registries,
                                               session1=source_session):
                LOG.warning('Skipping upload for image %s' % image_name)
                return []

        dockerc = Client(base_url='unix://var/run/docker.sock', version='auto')
        DockerImageUploader._pull(dockerc, repo, tag=source_tag)

        if modify_role:
            BaseImageUploader.run_modify_playbook(
                modify_role, modify_vars, source_image,
                target_image_source_tag, append_tag)
            # raise an exception if the playbook didn't tag
            # the expected target image
            dockerc.inspect_image(target_image)
        else:
            response = dockerc.tag(
                image=source_image, repository=target_image_no_tag,
                tag=target_tag, force=True
            )
            LOG.debug(response)

        DockerImageUploader._push(dockerc, target_image_no_tag, tag=target_tag)

        LOG.warning('Completed upload for image %s' % image_name)
        if cleanup == CLEANUP_NONE:
            return []
        if cleanup == CLEANUP_PARTIAL:
            return [source_image]
        return [source_image, target_image]

    @staticmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _pull(dockerc, image, tag=None):
        LOG.info('Pulling %s' % image)

        for line in dockerc.pull(image, tag=tag, stream=True):
            status = json.loads(line)
            if 'error' in status:
                LOG.warning('docker pull failed: %s' % status['error'])
                raise ImageUploaderException('Could not pull image %s' % image)

    @staticmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _push(dockerc, image, tag=None):
        LOG.info('Pushing %s' % image)

        for line in dockerc.push(image, tag=tag, stream=True):
            status = json.loads(line)
            if 'error' in status:
                LOG.warning('docker push failed: %s' % status['error'])
                raise ImageUploaderException('Could not push image %s' % image)

    def cleanup(self, local_images):
        if not local_images:
            return []

        dockerc = Client(base_url='unix://var/run/docker.sock', version='auto')
        for image in sorted(local_images):
            if not image:
                continue
            LOG.warning('Removing local copy of %s' % image)
            try:
                dockerc.remove_image(image)
            except docker.errors.APIError as e:
                if e.explanation:
                    LOG.error(e.explanation)
                else:
                    LOG.error(e)

    def run_tasks(self):
        if not self.upload_tasks:
            return
        local_images = []

        # Pull a single image first, to avoid duplicate pulls of the
        # same base layers
        first = self.upload_tasks.pop()
        result = self.upload_image(*first)
        local_images.extend(result)

        # workers will be based on CPU count with a min 4, max 12
        workers = min(12, max(4, processutils.get_worker_count()))
        p = futures.ThreadPoolExecutor(max_workers=workers)

        for result in p.map(docker_upload, self.upload_tasks):
            local_images.extend(result)
        LOG.info('result %s' % local_images)

        # Do cleanup after all the uploads so common layers don't get deleted
        # repeatedly
        self.cleanup(local_images)


class SkopeoImageUploader(BaseImageUploader):
    """Upload images using skopeo copy"""

    @staticmethod
    def upload_image(image_name, pull_source, push_destination,
                     insecure_registries, append_tag, modify_role,
                     modify_vars, dry_run, cleanup, image_layers):
        LOG.info('imagename: %s' % image_name)
        names = BaseImageUploader.source_target_names(
            image_name, pull_source, push_destination, append_tag)

        source_image = names['source_image']
        source_image_url = BaseImageUploader._image_to_url(source_image)
        source_image_local_url = parse.urlparse('containers-storage:%s'
                                                % source_image)
        source_insecure = source_image_url.netloc in insecure_registries

        append_tag = names['append_tag']

        target_image_source_tag = names['target_image_source_tag']
        target_image = names['target_image']
        target_image_url = BaseImageUploader._image_to_url(target_image)
        target_image_local_url = parse.urlparse('containers-storage:%s' %
                                                target_image)
        target_insecure = target_image_local_url.netloc in insecure_registries

        if dry_run:
            return []

        target_session = BaseImageUploader.authenticate(
            target_image_url, insecure=target_insecure)

        if modify_role and BaseImageUploader._image_exists(
                target_image, insecure_registries, target_session):
            LOG.warning('Skipping upload for modified image %s' %
                        target_image)
            return []

        source_session = BaseImageUploader.authenticate(
            source_image_url, insecure=source_insecure)

        source_inspect = BaseImageUploader._inspect(
            source_image_url, insecure=source_insecure, session=source_session)
        source_layers = source_inspect.get('Layers', [])
        BaseImageUploader._cross_repo_mount(
            target_image_url, image_layers, source_layers, insecure_registries,
            session=source_session)
        to_cleanup = []

        if modify_role:

            # Copy from source registry to local storage
            SkopeoImageUploader._copy(
                source_image_url,
                source_image_local_url,
                insecure_registries
            )
            if cleanup in (CLEANUP_FULL, CLEANUP_PARTIAL):
                to_cleanup = [source_image]

            BaseImageUploader.run_modify_playbook(
                modify_role, modify_vars, source_image,
                target_image_source_tag, append_tag,
                container_build_tool='buildah')
            if cleanup == CLEANUP_FULL:
                to_cleanup.append(target_image)

            # Copy from local storage to target registry
            SkopeoImageUploader._copy(
                target_image_local_url,
                target_image_url,
                insecure_registries
            )
            for layer in source_layers:
                image_layers.setdefault(layer, target_image_url)
            LOG.warning('Completed modify and upload for image %s' %
                        image_name)
        else:
            SkopeoImageUploader._copy(
                source_image_url,
                target_image_url,
                insecure_registries
            )
            LOG.warning('Completed upload for image %s' % image_name)
        for layer in source_layers:
            image_layers.setdefault(layer, target_image_url)
        return to_cleanup

    @staticmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _copy(source_url, target_url, insecure_registries):
        source = source_url.geturl()
        target = target_url.geturl()
        LOG.info('Copying from %s to %s' % (source, target))
        cmd = ['skopeo', 'copy']

        if source_url.netloc in insecure_registries:
            cmd.append('--src-tls-verify=false')

        if target_url.netloc in insecure_registries:
            cmd.append('--dest-tls-verify=false')

        cmd.append(source)
        cmd.append(target)
        LOG.info('Running %s' % ' '.join(cmd))
        env = os.environ.copy()
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE)

        out, err = process.communicate()
        LOG.info(out)
        if process.returncode != 0:
            raise ImageUploaderException('Error copying image:\n%s\n%s' %
                                         (' '.join(cmd), err))
        return out

    @staticmethod
    def _delete(image_url, insecure=False):
        image = image_url.geturl()
        LOG.info('Deleting %s' % image)
        cmd = ['skopeo', 'delete']

        if insecure:
            cmd.append('--tls-verify=false')
        cmd.append(image)
        LOG.info('Running %s' % ' '.join(cmd))
        env = os.environ.copy()
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE)

        out, err = process.communicate()
        LOG.info(out)
        if process.returncode != 0:
            raise ImageUploaderException('Error deleting image:\n%s\n%s' %
                                         (' '.join(cmd), err))
        return out

    def cleanup(self, local_images):
        if not local_images:
            return []

        for image in sorted(local_images):
            if not image:
                continue
            LOG.warning('Removing local copy of %s' % image)
            image_url = parse.urlparse('containers-storage:%s' % image)
            SkopeoImageUploader._delete(image_url)

    def run_tasks(self):
        if not self.upload_tasks:
            return
        local_images = []

        # Pull a single image first, to avoid duplicate pulls of the
        # same base layers
        first = self.upload_tasks.pop()
        result = self.upload_image(*first)
        local_images.extend(result)

        # workers will be half the CPU count, to a minimum of 2
        workers = max(2, processutils.get_worker_count() // 2)
        p = futures.ThreadPoolExecutor(max_workers=workers)

        for result in p.map(skopeo_upload, self.upload_tasks):
            local_images.extend(result)
        LOG.info('result %s' % local_images)

        # Do cleanup after all the uploads so common layers don't get deleted
        # repeatedly
        self.cleanup(local_images)


def docker_upload(args):
    return DockerImageUploader.upload_image(*args)


def skopeo_upload(args):
    return SkopeoImageUploader.upload_image(*args)


def discover_tag_from_inspect(args):
    image, tag_from_label, insecure_registries = args
    image_url = BaseImageUploader._image_to_url(image)
    insecure = image_url.netloc in insecure_registries
    session = BaseImageUploader.authenticate(image_url, insecure=insecure)
    i = BaseImageUploader._inspect(image_url, insecure=insecure,
                                   session=session)
    if ':' in image_url.path:
        # break out the tag from the url to be the fallback tag
        path = image.rpartition(':')
        fallback_tag = path[2]
        image = path[0]
    else:
        fallback_tag = None
    return image, BaseImageUploader._discover_tag_from_inspect(
        i, image, tag_from_label, fallback_tag)
