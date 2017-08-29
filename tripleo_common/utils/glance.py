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

import collections

from glanceclient import exc as exceptions
from glanceclient.v2.client import Client as real_glance_client


def create_or_find_kernel_and_ramdisk(glanceclient, kernel_name, ramdisk_name,
                                      kernel_path=None, ramdisk_path=None,
                                      skip_missing=False):
    """Find or create a given kernel and ramdisk in Glance.

    If either kernel_path or ramdisk_path is None, they will not be created,
    and an exception will be raised if it does not exist in Glance.

    :param glanceclient: A client for Glance.
    :param kernel_name: Name to search for or create for the kernel.
    :param ramdisk_name: Name to search for or create for the ramdisk.
    :param kernel_path: Path to the kernel on disk.
    :param ramdisk_path: Path to the ramdisk on disk.
    :param skip_missing: If `True', do not raise an exception if either the
                         kernel or ramdisk image is not found.

    :returns: A dictionary mapping kernel or ramdisk to the ID in Glance.
    """
    kernel_image = _upload_file(glanceclient, kernel_name, kernel_path,
                                'aki', 'Kernel', skip_missing=skip_missing)
    ramdisk_image = _upload_file(glanceclient, ramdisk_name, ramdisk_path,
                                 'ari', 'Ramdisk', skip_missing=skip_missing)
    return {'kernel': kernel_image.id, 'ramdisk': ramdisk_image.id}


def _upload_file(glanceclient, name, path, disk_format, type_name,
                 skip_missing=False):
    image_tuple = collections.namedtuple('image', ['id'])
    try:
        if isinstance(glanceclient, real_glance_client):
            images = glanceclient.images.list(name=name,
                                              disk_format=disk_format)
            image = None
            for img in images:
                if ((img['name'] == name or img['id'] == name) and
                        img['disk_format'] == disk_format):
                    image = img
            if not image:
                raise exceptions.NotFound("No image found")
        else:
            # TODO(dprince) remove this
            # This code expects the python-openstackclient version of
            # "glanceclient" (which isn't pure python-glanceclient) and is
            # here for backwards compat until python-tripleoclient starts
            # using the Mistral API for this functionality.
            image = glanceclient.images.find(name=name,
                                             disk_format=disk_format)
    except exceptions.NotFound:
        if path:
            image = glanceclient.images.create(
                name=name, disk_format=disk_format, is_public=True,
                data=open(path, 'rb'))
        else:
            if skip_missing:
                image = image_tuple(None)
            else:
                raise ValueError("%s image not found in Glance, and no path "
                                 "specified." % type_name)
    return image
