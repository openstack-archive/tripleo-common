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
import json
import logging
import multiprocessing
import netifaces
import os
import requests
import six
from six.moves import urllib
import subprocess
import tenacity

import docker
try:
    from docker import APIClient as Client
except ImportError:
    from docker import Client
from oslo_concurrency import processutils
from tripleo_common.image.base import BaseImageManager
from tripleo_common.image.exception import ImageNotFoundException
from tripleo_common.image.exception import ImageUploaderException


LOG = logging.getLogger(__name__)


SECURE_REGISTRIES = (
    'trunk.registry.rdoproject.org',
    'docker.io',
)


class ImageUploadManager(BaseImageManager):
    """Manage the uploading of image files

       Manage the uploading of images from a config file specified in YAML
       syntax. Multiple config files can be specified. They will be merged.
       """

    def __init__(self, config_files=None, verbose=False, debug=False):
        if config_files is None:
            config_files = []
        super(ImageUploadManager, self).__init__(config_files)
        self.uploaders = {}

    def discover_image_tag(self, image, tag_from_label=None):
        uploader = self.uploader('docker')
        return uploader.discover_image_tag(
            image, tag_from_label=tag_from_label)

    def uploader(self, uploader):
        if uploader not in self.uploaders:
            self.uploaders[uploader] = ImageUploader.get_uploader(uploader)
        return self.uploaders[uploader]

    def upload(self):
        """Start the upload process"""

        LOG.info('Using config files: %s' % self.config_files)

        uploads = self.load_config_files(self.UPLOADS) or []
        container_images = self.load_config_files(self.CONTAINER_IMAGES) or []
        upload_images = uploads + container_images
        default_push_destination = self.get_ctrl_plane_ip() + ':8787'

        for item in upload_images:
            image_name = item.get('imagename')
            uploader = item.get('uploader', 'docker')
            pull_source = item.get('pull_source')
            push_destination = item.get('push_destination',
                                        default_push_destination)

            # This updates the parsed upload_images dict with real values
            item['push_destination'] = push_destination

            self.uploader(uploader).add_upload_task(
                image_name, pull_source, push_destination)

        for uploader in self.uploaders.values():
            uploader.run_tasks()

        return upload_images  # simply to make test validation easier

    def get_ctrl_plane_ip(self):
        addr = 'localhost'
        if 'br-ctlplane' in netifaces.interfaces():
            addrs = netifaces.ifaddresses('br-ctlplane')
            if netifaces.AF_INET in addrs and addrs[netifaces.AF_INET]:
                addr = addrs[netifaces.AF_INET][0].get('addr', 'localhost')
        return addr


@six.add_metaclass(abc.ABCMeta)
class ImageUploader(object):
    """Base representation of an image uploading method"""

    @staticmethod
    def get_uploader(uploader):
        if uploader == 'docker':
            return DockerImageUploader()
        raise ImageUploaderException('Unknown image uploader type')

    @abc.abstractmethod
    def run_tasks(self):
        """Run all tasks"""
        pass

    @abc.abstractmethod
    def add_upload_task(self, image_name, pull_source, push_destination):
        """Add an upload task to be executed later"""
        pass

    @abc.abstractmethod
    def discover_image_tag(self, image, tag_from_label=None):
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


class DockerImageUploader(ImageUploader):
    """Upload images using docker push"""

    def __init__(self):
        self.upload_tasks = []
        self.secure_registries = set()
        self.insecure_registries = set()

    @staticmethod
    def upload_image(image_name, pull_source, push_destination,
                     insecure_registries):
        LOG.info('imagename: %s' % image_name)
        dockerc = Client(base_url='unix://var/run/docker.sock', version='auto')
        if ':' in image_name:
            image = image_name.rpartition(':')[0]
            tag = image_name.rpartition(':')[2]
        else:
            image = image_name
            tag = 'latest'
        if pull_source:
            repo = pull_source + '/' + image
        else:
            repo = image

        full_image = repo + ':' + tag
        new_repo = push_destination + '/' + repo.partition('/')[2]
        full_new_repo = new_repo + ':' + tag

        if DockerImageUploader._images_match(full_image, full_new_repo,
                                             insecure_registries):
            LOG.info('Skipping upload for image %s' % image_name)
            return []

        DockerImageUploader._pull(dockerc, repo, tag=tag)

        response = dockerc.tag(image=full_image, repository=new_repo,
                               tag=tag, force=True)
        LOG.debug(response)

        DockerImageUploader._push(dockerc, new_repo, tag=tag)

        LOG.info('Completed upload for image %s' % image_name)
        return full_image, full_new_repo

    @staticmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _pull(dockerc, image, tag=None):
        LOG.debug('Pulling %s' % image)

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
        LOG.debug('Pushing %s' % image)

        for line in dockerc.push(image, tag=tag, stream=True):
            status = json.loads(line)
            if 'error' in status:
                LOG.warning('docker push failed: %s' % status['error'])
                raise ImageUploaderException('Could not push image %s' % image)

    @staticmethod
    def _images_match(image1, image2, insecure_registries):
        try:
            image1_digest = DockerImageUploader._image_digest(
                image1, insecure_registries)
        except Exception:
            return False
        try:
            image2_digest = DockerImageUploader._image_digest(
                image2, insecure_registries)
        except Exception:
            return False

        # missing digest, no way to know if they match
        if not image1_digest or not image2_digest:
            return False
        return image1_digest == image2_digest

    @staticmethod
    def _image_digest(image, insecure_registries):
        image_url = DockerImageUploader._image_to_url(image)
        insecure = image_url.netloc in insecure_registries
        i = DockerImageUploader._inspect(image_url.geturl(), insecure)
        return i.get('Digest')

    @staticmethod
    @tenacity.retry(  # Retry up to 5 times with jittered exponential backoff
        reraise=True,
        retry=tenacity.retry_if_exception_type(ImageUploaderException),
        wait=tenacity.wait_random_exponential(multiplier=1, max=10),
        stop=tenacity.stop_after_attempt(5)
    )
    def _inspect(image, insecure=False):

        cmd = ['skopeo', 'inspect']

        if insecure:
            cmd.append('--tls-verify=false')
        cmd.append(image)

        LOG.info('Running %s' % ' '.join(cmd))
        env = os.environ.copy()
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)

        out, err = process.communicate()
        if process.returncode != 0:
            not_found_msgs = (
                'manifest unknown',
                # returned by docker.io
                'requested access to the resource is denied'
            )
            if any(n in err for n in not_found_msgs):
                raise ImageNotFoundException('Not found image: %s\n%s' %
                                             (image, err))
            raise ImageUploaderException('Error inspecting image: %s\n%s' %
                                         (image, err))
        return json.loads(out)

    @staticmethod
    def _image_to_url(image):
        if '://' not in image:
            image = 'docker://' + image
        return urllib.parse.urlparse(image)

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
        p = multiprocessing.Pool(16)

        versioned_images = {}
        for image, versioned_image in p.map(discover_tag_from_inspect,
                                            discover_args):
            versioned_images[image] = versioned_image
        return versioned_images

    def discover_image_tag(self, image, tag_from_label=None,
                           fallback_tag=None):
        image_url = self._image_to_url(image)
        insecure = self.is_insecure_registry(image_url.netloc)
        i = self._inspect(image_url.geturl(), insecure)
        return self._discover_tag_from_inspect(i, image, tag_from_label,
                                               fallback_tag)

    def cleanup(self, local_images):
        dockerc = Client(base_url='unix://var/run/docker.sock', version='auto')
        for image in sorted(local_images):
            if not image:
                continue
            LOG.info('Removing local copy of %s' % image)
            try:
                dockerc.remove_image(image)
            except docker.errors.APIError as e:
                if e.explanation:
                    LOG.warning(e.explanation)
                else:
                    LOG.warning(e)

    def add_upload_task(self, image_name, pull_source, push_destination):
        # prime self.insecure_registries
        if pull_source:
            self.is_insecure_registry(self._image_to_url(pull_source).netloc)
        else:
            self.is_insecure_registry(self._image_to_url(image_name).netloc)
        self.is_insecure_registry(self._image_to_url(push_destination).netloc)
        self.upload_tasks.append((image_name, pull_source, push_destination,
                                  self.insecure_registries))

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
        p = multiprocessing.Pool(workers)

        for result in p.map(docker_upload, self.upload_tasks):
            local_images.extend(result)
        LOG.info('result %s' % local_images)

        # Do cleanup after all the uploads so common layers don't get deleted
        # repeatedly
        self.cleanup(local_images)

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


def docker_upload(args):
    return DockerImageUploader.upload_image(*args)


def discover_tag_from_inspect(args):
    image, tag_from_label, insecure_registries = args
    image_url = DockerImageUploader._image_to_url(image)
    insecure = image_url.netloc in insecure_registries
    i = DockerImageUploader._inspect(image_url.geturl(), insecure)
    if ':' in image_url.path:
        # break out the tag from the url to be the fallback tag
        path = image.rpartition(':')
        fallback_tag = path[2]
        image = path[0]
    else:
        fallback_tag = None
    return image, DockerImageUploader._discover_tag_from_inspect(
        i, image, tag_from_label, fallback_tag)
