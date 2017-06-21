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


import jinja2
import logging
import os
import re
import subprocess
import sys
import yaml

from tripleo_common.image import base


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

    def container_images_from_template(self, filter=None, **kwargs):
        '''Build container_images data from container_images_template.

        Any supplied keyword arguments are used for the substitution mapping to
        transform the data in the config file container_images_template
        section.

        The resulting data resembles a config file which contains a valid
        populated container_images section.

        If a function is passed to the filter argument, this will be used to
        modify the entry after substitution. If the filter function returns
        None then the entry will not be added to the resulting list.

        Defaults are applied so that when no arguments are provided the
        resulting entries have the form:
        - imagename: tripleoupstream/centos-binary-<name>:latest
        '''
        mapping = dict(kwargs)

        result = []

        if len(self.config_files) != 1:
            raise ValueError('A single config file must be specified')
        config_file = self.config_files[0]
        with open(config_file) as cf:
            template = jinja2.Template(cf.read())

        rendered = template.render(mapping)
        rendered_dict = yaml.safe_load(rendered)
        for i in rendered_dict[self.CONTAINER_IMAGES_TEMPLATE]:
            entry = dict(i)
            if filter:
                entry = filter(entry)
            if entry is not None:
                result.append(entry)
        return result

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
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE)
        out, err = process.communicate()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd, err)
        return out
