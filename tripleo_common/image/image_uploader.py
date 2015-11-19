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
import logging
import six

from docker import Client
from tripleo_common.image.base import BaseImageManager
from tripleo_common.image.exception import ImageUploaderException


class ImageUploadManager(BaseImageManager):
    """Manage the uploading of image files

       Manage the uploading of images from a config file specified in YAML
       syntax. Multiple config files can be specified. They will be merged.
       """
    logger = logging.getLogger(__name__ + '.ImageUploadManager')

    def __init__(self, config_files, verbose=False, debug=False):
        super(ImageUploadManager, self).__init__(config_files)

    def upload(self):
        """Start the upload process"""

        self.logger.info('Using config files: %s' % self.config_files)

        upload_images = self.load_config_files(self.CONFIG_SECTIONS[1])

        for item in upload_images:
            image_name = item.get('imagename')
            uploader = item.get('uploader')
            pull_source = item.get('pull_source')
            push_destination = item.get('push_destination')

            self.logger.info('imagename: %s' % image_name)

            uploader = ImageUploader.get_uploader(uploader)
            uploader.upload_image(image_name, pull_source, push_destination)

        return upload_images  # simply to make test validation easier


@six.add_metaclass(abc.ABCMeta)
class ImageUploader(object):
    """Base representation of an image uploading method"""

    @staticmethod
    def get_uploader(uploader):
        if uploader == 'docker':
            return DockerImageUploader()
        raise ImageUploaderException('Unknown image uploader type')

    @abc.abstractmethod
    def upload_image(self, image_name, pull_source, push_destination):
        """Upload a disk image"""
        pass


class DockerImageUploader(ImageUploader):
    """Upload images using docker push"""

    logger = logging.getLogger(__name__ + '.DockerImageUploader')

    def upload_image(self, image_name, pull_source, push_destination):
        dockerc = Client(base_url='unix://var/run/docker.sock')
        image = image_name.rpartition(':')[0]
        tag = image_name.rpartition(':')[2]
        repo = pull_source + '/' + image

        response = [line for line in dockerc.pull(repo,
                    tag=tag, stream=True, insecure_registry=True)]
        self.logger.debug(response)

        full_image = repo + ':' + tag
        new_repo = push_destination + '/' + image
        response = dockerc.tag(image=full_image, repository=new_repo,
                               tag=tag, force=True)
        self.logger.debug(response)

        response = [line for line in dockerc.push(new_repo,
                    tag=tag, stream=True, insecure_registry=True)]
        self.logger.debug(response)

        self.logger.info('Completed upload for docker image %s' % image_name)
