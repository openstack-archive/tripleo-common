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


from concurrent import futures
import json
import netifaces
import os
import re
import requests
from requests import auth as requests_auth
import shutil
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

    def __init__(self, config_files=None,
                 dry_run=False, cleanup=CLEANUP_FULL,
                 mirrors=None):
        if config_files is None:
            config_files = []
        super(ImageUploadManager, self).__init__(config_files)
        self.uploaders = {
            'docker': DockerImageUploader(),
            'skopeo': SkopeoImageUploader()
        }
        self.dry_run = dry_run
        self.cleanup = cleanup
        self.mirrors = mirrors

    def discover_image_tag(self, image, tag_from_label=None,
                           username=None, password=None):
        uploader = self.uploader(DEFAULT_UPLOADER)
        return uploader.discover_image_tag(
            image, tag_from_label=tag_from_label,
            username=username, password=password, mirrors=self.mirrors)

    def uploader(self, uploader):
        if uploader not in self.uploaders:
            raise ImageUploaderException('Unknown image uploader type')
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

            uploader = self.uploader(uploader)
            task = UploadTask(
                image_name, pull_source, push_destination,
                append_tag, modify_role, modify_vars, self.dry_run,
                self.cleanup, self.mirrors)
            uploader.add_upload_task(task)

        for uploader in self.uploaders.values():
            uploader.run_tasks()

        return upload_images  # simply to make test validation easier

    def get_uploader(self, uploader):
        if uploader == 'docker':
            return DockerImageUploader()
        if uploader == 'skopeo':
            return SkopeoImageUploader()
        raise ImageUploaderException('Unknown image uploader type')


class BaseImageUploader(object):

    insecure_registries = set()
    secure_registries = set(SECURE_REGISTRIES)

    def __init__(self):
        self.upload_tasks = []
        # A mapping of layer hashs to the image which first copied that
        # layer to the target
        self.image_layers = {}

    @classmethod
    def init_registries_cache(cls):
        cls.insecure_registries.clear()
        cls.secure_registries.clear()
        cls.secure_registries.update(SECURE_REGISTRIES)

    def cleanup(self):
        pass

    def run_tasks(self):
        pass

    @classmethod
    def run_modify_playbook(cls, modify_role, modify_vars,
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

    @classmethod
    def _images_match(cls, image1, image2, session1=None, mirrors=None):
        try:
            image1_digest = cls._image_digest(image1, session=session1,
                                              mirrors=mirrors)
        except Exception:
            return False
        try:
            image2_digest = cls._image_digest(image2, mirrors=mirrors)
        except Exception:
            return False

        # missing digest, no way to know if they match
        if not image1_digest or not image2_digest:
            return False
        return image1_digest == image2_digest

    @classmethod
    def _image_digest(cls, image, session=None, mirrors=None):
        image_url = cls._image_to_url(image)
        insecure = image_url.netloc in cls.insecure_registries
        i = cls._inspect(image_url, insecure, session, mirrors=mirrors)
        return i.get('Digest')

    @classmethod
    def _image_labels(cls, image_url, insecure, session=None, mirrors=None):
        i = cls._inspect(image_url, insecure, session, mirrors=mirrors)
        return i.get('Labels', {}) or {}

    @classmethod
    def _image_exists(cls, image, session=None, mirrors=None):
        try:
            cls._image_digest(
                image, session=session, mirrors=mirrors)
        except ImageNotFoundException:
            return False
        else:
            return True

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def authenticate(cls, image_url, username=None, password=None,
                     insecure=False, mirrors=None):
        image, tag = image_url.path.split(':')
        url = cls._build_url(image_url, path='/',
                             insecure=insecure,
                             mirrors=mirrors)
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

    @classmethod
    def _build_url(cls, url, path, insecure=False, mirrors=None):
        netloc = url.netloc
        if mirrors and netloc in mirrors:
            mirror = mirrors[netloc]
            return '%sv2%s' % (mirror, path)
        else:
            if insecure:
                scheme = 'http'
            else:
                scheme = 'https'
            if netloc == 'docker.io':
                netloc = 'registry-1.docker.io'
            return '%s://%s/v2%s' % (scheme, netloc, path)

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(
            requests.exceptions.RequestException
        ),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _inspect(cls, image_url, insecure=False, session=None, mirrors=None):
        image, tag = image_url.path.split(':')
        parts = {
            'image': image,
            'tag': tag
        }

        manifest_url = cls._build_url(
            image_url, '%(image)s/manifests/%(tag)s' % parts,
            insecure, mirrors
        )
        tags_url = cls._build_url(
            image_url, '%(image)s/tags/list' % parts,
            insecure, mirrors
        )
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
        config_url = cls._build_url(
            image_url, '%(image)s/blobs/%(config_digest)s' % parts,
            insecure, mirrors)
        config_f = p.submit(
            session.get, config_url, headers=config_headers, timeout=30)
        config_r = config_f.result()
        config_r.raise_for_status()

        tags = tags_r.json()['tags']
        digest = manifest_r.headers['Docker-Content-Digest']
        config = config_r.json()
        name = '%s%s' % (image_url.netloc, image)

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

    def discover_image_tags(self, images, tag_from_label=None, mirrors=None):
        image_urls = [self._image_to_url(i) for i in images]

        # prime self.insecure_registries by testing every image
        for url in image_urls:
            self.is_insecure_registry(url.netloc)

        discover_args = []
        for image in images:
            discover_args.append((image, tag_from_label,
                                  self.insecure_registries, mirrors))
        p = futures.ThreadPoolExecutor(max_workers=16)

        versioned_images = {}
        for image, versioned_image in p.map(discover_tag_from_inspect,
                                            discover_args):
            versioned_images[image] = versioned_image
        return versioned_images

    def discover_image_tag(self, image, tag_from_label=None,
                           fallback_tag=None, username=None, password=None,
                           mirrors=None):
        image_url = self._image_to_url(image)
        insecure = self.is_insecure_registry(image_url.netloc)
        session = self.authenticate(
            image_url, insecure=insecure, username=username, password=password,
            mirrors=mirrors)
        i = self._inspect(image_url, insecure, session, mirrors=mirrors)
        return self._discover_tag_from_inspect(i, image, tag_from_label,
                                               fallback_tag)

    def filter_images_with_labels(self, images, labels,
                                  username=None, password=None, mirrors=None):
        images_with_labels = []
        for image in images:
            url = self._image_to_url(image)
            insecure = self.is_insecure_registry(url.netloc)
            session = self.authenticate(
                url, insecure=insecure, username=username, password=password,
                mirrors=mirrors)
            image_labels = self._image_labels(
                url, insecure=insecure, session=session, mirrors=mirrors)
            if set(labels).issubset(set(image_labels)):
                images_with_labels.append(image)

        return images_with_labels

    def add_upload_task(self, task):
        # prime insecure_registries
        if task.pull_source:
            self.is_insecure_registry(
                self._image_to_url(task.pull_source).netloc)
        else:
            self.is_insecure_registry(
                self._image_to_url(task.image_name).netloc)
        self.is_insecure_registry(
            self._image_to_url(task.push_destination).netloc)
        self.upload_tasks.append((self, task))

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

    @classmethod
    def _cross_repo_mount(cls, target_image_url, image_layers,
                          source_layers, session):
        netloc = target_image_url.netloc
        name = target_image_url.path.split(':')[0][1:]
        if netloc in cls.insecure_registries:
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

    def upload_image(self, task):
        t = task
        LOG.info('imagename: %s' % t.image_name)
        insecure_registries = self.insecure_registries
        source_insecure = t.source_image_url.netloc in insecure_registries
        target_insecure = t.target_image_url.netloc in insecure_registries

        if t.dry_run:
            return []

        if t.modify_role:
            target_session = self.authenticate(
                t.target_image_url, insecure=target_insecure,
                mirrors=t.mirrors)
            if self._image_exists(t.target_image,
                                  session=target_session,
                                  mirrors=t.mirrors):
                LOG.warning('Skipping upload for modified image %s' %
                            t.target_image)
                return []
        else:
            source_session = self.authenticate(
                t.source_image_url, insecure=source_insecure,
                mirrors=t.mirrors)
            if self._images_match(t.source_image, t.target_image,
                                  session1=source_session, mirrors=t.mirrors):
                LOG.warning('Skipping upload for image %s' % t.image_name)
                return []

        dockerc = Client(base_url='unix://var/run/docker.sock', version='auto')
        self._pull(dockerc, t.repo, tag=t.source_tag)

        if t.modify_role:
            self.run_modify_playbook(
                t.modify_role, t.modify_vars, t.source_image,
                t.target_image_source_tag, t.append_tag)
            # raise an exception if the playbook didn't tag
            # the expected target image
            dockerc.inspect_image(t.target_image)
        else:
            response = dockerc.tag(
                image=t.source_image, repository=t.target_image_no_tag,
                tag=t.target_tag, force=True
            )
            LOG.debug(response)

        self._push(dockerc, t.target_image_no_tag, tag=t.target_tag)

        LOG.warning('Completed upload for image %s' % t.image_name)
        if t.cleanup == CLEANUP_NONE:
            return []
        if t.cleanup == CLEANUP_PARTIAL:
            return [t.source_image]
        return [t.source_image, t.target_image]

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _pull(cls, dockerc, image, tag=None):
        LOG.info('Pulling %s' % image)

        for line in dockerc.pull(image, tag=tag, stream=True):
            status = json.loads(line)
            if 'error' in status:
                LOG.warning('docker pull failed: %s' % status['error'])
                raise ImageUploaderException('Could not pull image %s' % image)

    @classmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _push(cls, dockerc, image, tag=None):
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
        uploader, first_task = self.upload_tasks.pop()
        result = uploader.upload_image(first_task)
        local_images.extend(result)

        # workers will be based on CPU count with a min 4, max 12
        workers = min(12, max(4, processutils.get_worker_count()))
        p = futures.ThreadPoolExecutor(max_workers=workers)

        for result in p.map(upload_task, self.upload_tasks):
            local_images.extend(result)
        LOG.info('result %s' % local_images)

        # Do cleanup after all the uploads so common layers don't get deleted
        # repeatedly
        self.cleanup(local_images)


class SkopeoImageUploader(BaseImageUploader):
    """Upload images using skopeo copy"""

    def upload_image(self, task):
        t = task
        LOG.info('imagename: %s' % t.image_name)
        insecure_registries = self.insecure_registries

        source_image_local_url = parse.urlparse('containers-storage:%s'
                                                % t.source_image)
        source_insecure = t.source_image_url.netloc in insecure_registries

        target_image_local_url = parse.urlparse('containers-storage:%s' %
                                                t.target_image)
        target_insecure = t.target_image_url.netloc in insecure_registries

        if t.dry_run:
            return []

        target_session = self.authenticate(
            t.target_image_url, insecure=target_insecure,
            mirrors=t.mirrors)

        if t.modify_role and self._image_exists(
                t.target_image, target_session,
                mirrors=t.mirrors):
            LOG.warning('Skipping upload for modified image %s' %
                        t.target_image)
            return []

        source_session = self.authenticate(
            t.source_image_url, insecure=source_insecure,
            mirrors=t.mirrors)

        source_inspect = self._inspect(
            t.source_image_url,
            insecure=source_insecure,
            session=source_session,
            mirrors=t.mirrors)
        source_layers = source_inspect.get('Layers', [])
        self._cross_repo_mount(
            t.target_image_url, self.image_layers, source_layers,
            session=source_session)
        to_cleanup = []

        if t.modify_role:

            # Copy from source registry to local storage
            self._copy(
                t.source_image_url,
                source_image_local_url
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
                t.target_image_url
            )
            for layer in source_layers:
                self.image_layers.setdefault(layer, t.target_image_url)
            LOG.warning('Completed modify and upload for image %s' %
                        t.image_name)
        else:
            self._copy(
                t.source_image_url,
                t.target_image_url
            )
            LOG.warning('Completed upload for image %s' % t.image_name)
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

        if source_url.netloc in cls.insecure_registries:
            cmd.append('--src-tls-verify=false')

        if target_url.netloc in cls.insecure_registries:
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

    @classmethod
    def _delete(cls, image_url, insecure=False):
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
            self._delete(image_url)

    def run_tasks(self):
        if not self.upload_tasks:
            return
        local_images = []

        # Pull a single image first, to avoid duplicate pulls of the
        # same base layers
        uploader, first_task = self.upload_tasks.pop()
        result = uploader.upload_image(first_task)
        local_images.extend(result)

        # workers will be half the CPU count, to a minimum of 2
        workers = max(2, processutils.get_worker_count() // 2)
        p = futures.ThreadPoolExecutor(max_workers=workers)

        for result in p.map(upload_task, self.upload_tasks):
            local_images.extend(result)
        LOG.info('result %s' % local_images)

        # Do cleanup after all the uploads so common layers don't get deleted
        # repeatedly
        self.cleanup(local_images)


class UploadTask(object):

    def __init__(self, image_name, pull_source, push_destination,
                 append_tag, modify_role, modify_vars, dry_run, cleanup,
                 mirrors):
        self.image_name = image_name
        self.pull_source = pull_source
        self.push_destination = push_destination
        self.append_tag = append_tag or ''
        self.modify_role = modify_role
        self.modify_vars = modify_vars
        self.dry_run = dry_run
        self.cleanup = cleanup
        self.mirrors = mirrors

        if ':' in image_name:
            image = image_name.rpartition(':')[0]
            self.source_tag = image_name.rpartition(':')[2]
        else:
            image = image_name
            self.source_tag = 'latest'
        if pull_source:
            self.repo = pull_source + '/' + image
        else:
            self.repo = image

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


def upload_task(args):
    uploader, task = args
    return uploader.upload_image(task)


def discover_tag_from_inspect(args):
    image, tag_from_label, insecure_registries, mirrors = args
    image_url = BaseImageUploader._image_to_url(image)
    insecure = image_url.netloc in insecure_registries
    session = BaseImageUploader.authenticate(image_url, insecure=insecure,
                                             mirrors=mirrors)
    i = BaseImageUploader._inspect(image_url, insecure=insecure,
                                   session=session, mirrors=mirrors)
    if ':' in image_url.path:
        # break out the tag from the url to be the fallback tag
        path = image.rpartition(':')
        fallback_tag = path[2]
        image = path[0]
    else:
        fallback_tag = None
    return image, BaseImageUploader._discover_tag_from_inspect(
        i, image, tag_from_label, fallback_tag)
