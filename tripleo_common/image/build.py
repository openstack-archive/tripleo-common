# Copyright 2015 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import os
import re

from oslo_log import log
from oslo_utils import strutils

import tripleo_common.arch
from tripleo_common.image.base import BaseImageManager
from tripleo_common.image.exception import ImageSpecificationException
from tripleo_common.image.image_builder import ImageBuilder


class ImageBuildManager(BaseImageManager):
    """Manage the building of image files

       Manage the building of images from a config file specified in YAML
       syntax. Multiple config files can be specified. They will be merged
       """
    logger = log.getLogger(__name__ + '.ImageBuildManager')

    APPEND_ATTRIBUTES = BaseImageManager.APPEND_ATTRIBUTES + ['environment']

    def __init__(self, config_files, images=None, output_directory='.',
                 skip=False):
        super(ImageBuildManager, self).__init__(config_files, images)
        self.output_directory = re.sub('[/]$', '', output_directory)
        self.skip = skip

    def build(self):
        """Start the build process"""

        self.logger.info('Using config files: %s' % self.config_files)

        disk_images = self.load_config_files(self.DISK_IMAGES)

        for image in disk_images:
            arch = image.get('arch', tripleo_common.arch.dib_arch())
            image_type = image.get('type', 'qcow2')
            image_name = image.get('imagename')
            builder = image.get('builder', 'dib')
            skip_base = strutils.bool_from_string(
                image.get('skip_base', False))
            docker_target = image.get('docker_target')
            node_dist = image.get('distro')
            if node_dist is None:
                raise ImageSpecificationException('distro is required')
            self.logger.info('imagename: %s' % image_name)
            image_extension = image.get('imageext', image_type)
            image_path = os.path.join(self.output_directory, image_name)
            if self.skip:
                self.logger.info('looking for image at path: %s' % image_path)
                if os.path.exists('%s.%s' % (image_path, image_extension)):
                    self.logger.info('Image file exists for image name: %s' %
                                     image_name)
                    self.logger.info('Skipping image build')
                    continue
            elements = image.get('elements', [])
            options = image.get('options', [])
            packages = image.get('packages', [])
            environment = image.get('environment', {})

            extra_options = {
                'skip_base': skip_base,
                'docker_target': docker_target,
                'environment': environment
            }

            builder = ImageBuilder.get_builder(builder)
            builder.build_image(image_path, image_type, node_dist, arch,
                                elements, options, packages, extra_options)
