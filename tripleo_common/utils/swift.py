# Copyright 2016 Red Hat, Inc.
# All Rights Reserved.
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

import logging
import os
import tempfile

from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
from tripleo_common.utils import tarball

from swiftclient.service import SwiftError
from swiftclient.service import SwiftUploadObject

LOG = logging.getLogger(__name__)


def empty_container(swiftclient, name):
    container_names = [container["name"] for container
                       in swiftclient.get_account()[1]]

    if name in container_names:
        headers, objects = swiftclient.get_container(name)
        # ensure container is a plan
        if headers.get(constants.TRIPLEO_META_USAGE_KEY) != 'plan':
            error_text = ("The {name} container does not contain a "
                          "TripleO deployment plan and was not "
                          "deleted.".format(name=name))
            raise ValueError(error_text)
        else:
            # FIXME(rbrady): remove delete_object loop when
            # LP#1615830 is fixed.  See LP#1615825 for more info.
            # delete files from plan
            for o in objects:
                swiftclient.delete_object(name, o['name'])
    else:
        error_text = "The {name} container does not exist.".format(name=name)
        raise ValueError(error_text)


def delete_container(swiftclient, name):
    try:
        empty_container(swiftclient, name)
        swiftclient.delete_container(name)
    except ValueError as e:
        # ValueError is raised when we can't find the container, which means
        # that it's already deleted.
        LOG.info(e.message)


def download_container(swiftclient, container, dest):
    """Download the contents of a Swift container to a directory"""

    objects = swiftclient.get_container(container)[1]

    for obj in objects:
        filename = obj['name']
        contents = swiftclient.get_object(container, filename)[1]
        path = os.path.join(dest, filename)
        dirname = os.path.dirname(path)

        if not os.path.exists(dirname):
            os.makedirs(dirname)

        with open(path, 'w') as f:
            f.write(contents)


def get_or_create_container(swiftclient, container):
    try:
        return swiftclient.get_container(container)
    except swiftexceptions.ClientException:
        LOG.debug("Container %s doesn't exist, creating...", container)
        return swiftclient.put_container(container)


def create_and_upload_tarball(swiftservice,
                              tmp_dir,
                              container,
                              tarball_name,
                              tarball_options='-czf',
                              delete_after=3600,
                              segment_size=1048576000,
                              use_slo=True,
                              segment_container=None,
                              leave_segments=False,
                              changed=None,
                              skip_identical=False,
                              fail_fast=True,
                              dir_marker=False):
    """Create a tarball containing the tmp_dir and upload it to Swift.

       This method allows to upload files bigger than 5GB.
       It will create 2 swift containers to store the segments and
       one container to reference the manifest with the segment pointers
    """

    try:
        with tempfile.NamedTemporaryFile() as tmp_tarball:
            tarball.create_tarball(tmp_dir,
                                   tmp_tarball.name,
                                   tarball_options)
            objs = [SwiftUploadObject(tmp_tarball,
                                      object_name=tarball_name)]
            options = {'meta': [],
                       'header': ['X-Delete-After: ' + str(delete_after)],
                       'segment_size': segment_size,
                       'use_slo': use_slo,
                       'segment_container': segment_container,
                       'leave_segments': leave_segments,
                       'changed': changed,
                       'skip_identical': skip_identical,
                       'fail_fast': fail_fast,
                       'dir_marker': dir_marker
                       }

            for r in swiftservice.upload(container,
                                         objs,
                                         options=options):
                if r['success']:
                    if 'object' in r:
                        LOG.info(r['object'])
                    elif 'for_object' in r:
                        LOG.info(
                            '%s segment %s' % (r['for_object'],
                                               r['segment_index'])
                            )
                else:
                    error = r['error']
                    if r['action'] == "create_container":
                        LOG.warning(
                            'Warning: failed to create container '
                            "'%s'%s", container, error
                        )
                    elif r['action'] == "upload_object":
                        LOG.error(
                            "Failed to upload object %s to container %s: %s" %
                            (container, r['object'], error)
                        )
                    else:
                        LOG.error("%s" % error)
    except SwiftError as e:
        LOG.error(e.value)
