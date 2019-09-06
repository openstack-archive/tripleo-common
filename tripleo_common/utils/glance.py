# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re

from glanceclient import exc as exceptions
from glanceclient.v2.client import Client as real_glance_client


def create_or_find_kernel_and_ramdisk(glanceclient, kernel_name, ramdisk_name):
    """Map kernel and ramdisk to file/HTTP path or Glance ID.

    An exception will be raised if kernel_name or ramdisk_name is not a path
    and instead refers to a non-existent Glance image.

    :param glanceclient: A client for Glance.
    :param kernel_name: Name to search for the kernel or path to kernel.
    :param ramdisk_name: Name to search for the ramdisk or path to ramdisk.

    :returns: A dictionary mapping kernel or ramdisk to path or Glance ID.
    """
    kernel_image = _check_image(glanceclient, kernel_name, disk_format='aki',
                                image_type='Kernel')
    ramdisk_image = _check_image(glanceclient, ramdisk_name, disk_format='ari',
                                 image_type='Ramdisk')
    return {'kernel': kernel_image, 'ramdisk': ramdisk_image}


def _check_image(glanceclient, name, disk_format, image_type):
    if re.match(r'^(file|https?)://', name):
        return name

    try:
        if isinstance(glanceclient, real_glance_client):
            images = glanceclient.images.list(name=name,
                                              disk_format=disk_format)
            image = None
            for img in images:
                if ((img['name'] == name or img['id'] == name) and
                        img['disk_format'] == disk_format):
                    image = img
                    break
        else:
            # TODO(dprince) remove this
            # This code expects the python-openstackclient version of
            # "glanceclient" (which isn't pure python-glanceclient) and is
            # here for backwards compat until python-tripleoclient starts
            # using the Mistral API for this functionality.
            image = glanceclient.images.find(name=name,
                                             disk_format=disk_format)
    except exceptions.NotFound:
        image = None

    if image:
        return image.id
    else:
        raise ValueError("%s image %s not found in Glance" % (image_type,
                                                              name))
