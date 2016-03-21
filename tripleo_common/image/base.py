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


import six

import os
import yaml

from oslo_log import log

from tripleo_common.image.exception import ImageSpecificationException


class BaseImageManager(object):
    logger = log.getLogger(__name__ + '.BaseImageManager')
    APPEND_ATTRIBUTES = ['elements', 'options', 'packages']

    def __init__(self, config_files):
        self.config_files = config_files

    def _extend_or_set_attribute(self, existing_image, image, attribute_name):
        attribute = image.get(attribute_name, [])
        if attribute:
            try:
                existing_image[attribute_name].extend(attribute)
            except KeyError:
                existing_image[attribute_name] = attribute

    def load_config_files(self):
        disk_images = {}
        for config_file in self.config_files:
            if os.path.isfile(config_file):
                with open(config_file) as cf:
                    images = yaml.load(cf.read()).get("disk_images")
                    self.logger.debug(
                        'disk_images JSON: %s' % str(disk_images))
                for image in images:
                    image_name = image.get('imagename')
                    if image_name is None:
                        msg = 'imagename is required'
                        self.logger.error(msg)
                        raise ImageSpecificationException(msg)

                    existing_image = disk_images.get(image_name)
                    if not existing_image:
                        disk_images[image_name] = image
                        continue

                    for attr in self.APPEND_ATTRIBUTES:
                        self._extend_or_set_attribute(existing_image, image,
                                                      attr)

                    # If a new key is introduced, add it.
                    for key, value in six.iteritems(image):
                        if key not in existing_image:
                            existing_image[key] = image[key]

                    disk_images[image_name] = existing_image

            else:
                self.logger.error('No config file exists at: %s' % config_file)
                raise IOError('No config file exists at: %s' % config_file)

        return [x for x in disk_images.values()]
