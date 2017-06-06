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

import collections
import json
import os
import yaml

from oslo_log import log

from tripleo_common.image.exception import ImageSpecificationException


class BaseImageManager(object):
    logger = log.getLogger(__name__ + '.BaseImageManager')
    APPEND_ATTRIBUTES = ['elements', 'options', 'packages']
    CONFIG_SECTIONS = (
        DISK_IMAGES, UPLOADS, CONTAINER_IMAGES,
        CONTAINER_IMAGES_TEMPLATE
    ) = (
        'disk_images', 'uploads', 'container_images',
        'container_images_template'
    )

    def __init__(self, config_files, images=None):
        self.config_files = config_files
        self.images = images

    def _extend_or_set_attribute(self, existing_image, image, attribute_name):
        attribute = image.get(attribute_name)
        if attribute:
            try:
                existing_image[attribute_name].update(attribute)
            except AttributeError:
                existing_image[attribute_name].extend(attribute)
            except KeyError:
                existing_image[attribute_name] = attribute

    def load_config_files(self, section):
        config_data = collections.OrderedDict()
        for config_file in self.config_files:
            if os.path.isfile(config_file):
                with open(config_file) as cf:
                    data = yaml.safe_load(cf.read()).get(section)
                    if not data:
                        return None
                    self.logger.debug('%s JSON: %s' % (section, str(data)))
                for item in data:
                    image_name = item.get('imagename')
                    if image_name is None:
                        msg = 'imagename is required'
                        self.logger.error(msg)
                        raise ImageSpecificationException(msg)

                    if self.images is not None and \
                            image_name not in self.images:
                        self.logger.debug('Image %s ignored' % image_name)
                        continue

                    existing_image = config_data.get(image_name)
                    if not existing_image:
                        config_data[image_name] = item
                        continue

                    for attr in self.APPEND_ATTRIBUTES:
                        self._extend_or_set_attribute(existing_image, item,
                                                      attr)

                    # If a new key is introduced, add it.
                    for key, value in item.items():
                        if key not in existing_image:
                            existing_image[key] = item[key]

                    config_data[image_name] = existing_image
            else:
                self.logger.error('No config file exists at: %s' % config_file)
                raise IOError('No config file exists at: %s' % config_file)
        return [x for x in config_data.values()]

    def json_output(self):
        self.logger.info('Using config files: %s' % self.config_files)
        disk_images = self.load_config_files(self.DISK_IMAGES)
        print(json.dumps(disk_images))
