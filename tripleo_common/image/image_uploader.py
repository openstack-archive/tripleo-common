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
import six
import time

import docker
try:
    from docker import APIClient as Client
except ImportError:
    from docker import Client
from tripleo_common.image.base import BaseImageManager
from tripleo_common.image.exception import ImageUploaderException


LOG = logging.getLogger(__name__)


class ImageUploadManager(BaseImageManager):
    """Manage the uploading of image files

       Manage the uploading of images from a config file specified in YAML
       syntax. Multiple config files can be specified. They will be merged.
       """
    logger = logging.getLogger(__name__ + '.ImageUploadManager')

    def __init__(self, config_files, verbose=False, debug=False):
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


class DockerImageUploader(ImageUploader):
    """Upload images using docker push"""

    def __init__(self):
        self.upload_tasks = []

    @staticmethod
    def upload_image(image_name, pull_source, push_destination):
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

        DockerImageUploader._pull_retry(dockerc, repo, tag=tag)

        full_image = repo + ':' + tag

        new_repo = push_destination + '/' + repo.partition('/')[2]
        full_new_repo = new_repo + ':' + tag

        response = dockerc.tag(image=full_image, repository=new_repo,
                               tag=tag, force=True)
        LOG.debug(response)

        response = [line for line in dockerc.push(new_repo,
                    tag=tag, stream=True)]
        LOG.debug(response)

        LOG.info('Completed upload for docker image %s' % image_name)
        return full_image, full_new_repo

    @staticmethod
    def _pull(dockerc, image, tag=None):
        LOG.debug('Pulling %s' % image)

        for line in dockerc.pull(image, tag=tag, stream=True):
            status = json.loads(line)
            if 'error' in status:
                LOG.warning('docker pull failed: %s' % status['error'])
                return 1
            LOG.debug(status.get('status'))
        return 0

    @staticmethod
    def _pull_retry(dockerc, image, tag=None):
        retval = -1
        count = 0
        while retval != 0:
            if count >= 5:
                raise ImageUploaderException('Could not pull image %s' % image)
            count += 1
            retval = DockerImageUploader._pull(dockerc, image, tag)
            if retval != 0:
                time.sleep(3)
                LOG.warning('retrying pulling image: %s' % image)

    def discover_image_tag(self, image, tag_from_label=None):
        dockerc = Client(base_url='unix://var/run/docker.sock', version='auto')

        image_name, colon, tag = image.rpartition(':')
        if not image_name:
            image_name = tag
            tag = None
        if not tag:
            tag = 'latest'
        image = '%s:%s' % (image_name, tag)

        DockerImageUploader._pull_retry(dockerc, image)
        i = dockerc.inspect_image(image)
        labels = i['Config']['Labels']

        label_keys = ', '.join(labels.keys())

        if not tag_from_label:
            raise ImageUploaderException(
                'No label specified. Available labels: %s' % label_keys
            )

        tag_label = labels.get(tag_from_label)
        if tag_label is None:
            raise ImageUploaderException(
                'Image %s has no label %s. Available labels: %s' %
                (image, tag_from_label, label_keys)
            )

        # confirm the tag exists by pulling it, which should be fast
        # because that image has just been pulled
        versioned_image = '%s:%s' % (image_name, tag_label)
        DockerImageUploader._pull_retry(dockerc, versioned_image)
        return tag_label

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
        self.upload_tasks.append((image_name, pull_source, push_destination))

    def run_tasks(self):
        if not self.upload_tasks:
            return
        local_images = []

        # Pull a single image first, to avoid duplicate pulls of the
        # same base layers
        first = self.upload_tasks.pop()
        result = self.upload_image(*first)
        local_images.extend(result)

        p = multiprocessing.Pool(4)

        for result in p.map(docker_upload, self.upload_tasks):
            local_images.extend(result)
        LOG.info('result %s' % local_images)

        # Do cleanup after all the uploads so common layers don't get deleted
        # repeatedly
        self.cleanup(local_images)


def docker_upload(args):
    return DockerImageUploader.upload_image(*args)
