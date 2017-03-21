#   Copyright 2017 Red Hat, Inc.
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


import logging
import os
import re
import subprocess
import sys

from tripleo_common.image import base

if sys.version_info[0] < 3:
    import codecs
    _open = open
    open = codecs.open


class KollaImageBuilder(base.BaseImageManager):
    """Build images using kolla-build"""

    logger = logging.getLogger(__name__ + '.KollaImageBuilder')
    handler = logging.StreamHandler(sys.stdout)

    @staticmethod
    def imagename_to_regex(imagename):
        if not imagename:
            return
        # remove any namespace from the start
        imagename = imagename.split('/')[-1]

        # remove any tag from the end
        imagename = imagename.split(':')[0]

        # remove supported base names from the start
        imagename = re.sub(r'^(centos|rhel)-', '', imagename)

        # remove install_type from the start
        imagename = re.sub(r'^(binary|source|rdo|rhos)-', '', imagename)

        # what results should be acceptable as a regex to build one image
        return imagename

    def build_images(self, kolla_config_files=None):

        cmd = ['kolla-build']
        if kolla_config_files:
            for f in kolla_config_files:
                cmd.append('--config-file')
                cmd.append(f)

        container_images = self.load_config_files(self.CONTAINER_IMAGES) or []
        container_images.sort(key=lambda i: i.get('imagename'))
        for i in container_images:
            image = self.imagename_to_regex(i.get('imagename'))
            if image:
                cmd.append(image)

        self.logger.info('Running %s' % ' '.join(cmd))
        env = os.environ.copy()
        process = subprocess.Popen(cmd, env=env)
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)
