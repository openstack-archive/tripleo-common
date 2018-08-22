# Copyright 2016 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import logging
import os

from oslo_concurrency import processutils

LOG = logging.getLogger(__name__)
DEFAULT_TARBALL_EXCLUDES = ['.git', '.tox', '*.pyc', '*.pyo']


def create_tarball(directory, filename, options='-czf',
                   excludes=DEFAULT_TARBALL_EXCLUDES):
    """Create a tarball of a directory."""
    LOG.debug('Creating tarball of %s at location %s' % (directory, filename))
    cmd = ['/usr/bin/tar', '-C', directory, options, filename]
    for x in excludes:
        cmd.extend(['--exclude', x])
    cmd.extend(['.'])
    processutils.execute(*cmd)


def tarball_extract_to_swift_container(object_client, filename, container):
    LOG.debug('Uploading filename %s to Swift container %s' % (filename,
                                                               container))
    with open(filename, 'rb') as f:
        object_client.put_object(
            container=container,
            obj='',
            contents=f,
            query_string='extract-archive=tar.gz',
            headers={'X-Detect-Content-Type': 'true'}
        )


def extract_tarball(directory, tarball, options='-xf', remove=False):
    """Extracts the tarball contained in the directory."""
    full_path = directory + '/' + tarball
    if not os.path.exists(full_path):
        LOG.debug('Tarball %s does not exist' % full_path)
    else:
        LOG.debug('Extracting tarball %s' % full_path)
        cmd = ['/usr/bin/tar', '-C', directory, options, full_path]
        processutils.execute(*cmd)
        if remove:
            LOG.debug('Removing tarball %s' % full_path)
            os.remove(full_path)
