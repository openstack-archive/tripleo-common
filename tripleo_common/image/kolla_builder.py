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
from tripleo_common.image import image_uploader


CONTAINER_IMAGES_DEFAULTS = {
    'namespace': 'docker.io/tripleomaster',
    'ceph_namespace': 'docker.io/ceph',
    'ceph_image': 'daemon',
    'ceph_tag': 'v3.0.3-stable-3.0-luminous-centos-7-x86_64',
    'name_prefix': 'centos-binary-',
    'name_suffix': '',
    'tag': 'current-tripleo',
    'neutron_driver': None,
    'logging': 'files'
}

DEFAULT_TEMPLATE_FILE = os.path.join(sys.prefix, 'share', 'tripleo-common',
                                     'container-images',
                                     'overcloud_containers.yaml.j2')


def container_images_prepare_defaults():
    return KollaImageBuilder.container_images_template_inputs()


def container_images_prepare(template_file=DEFAULT_TEMPLATE_FILE,
                             excludes=None, service_filter=None,
                             pull_source=None, push_destination=None,
                             mapping_args=None, output_env_file=None,
                             output_images_file=None, tag_from_label=None):

    if mapping_args is None:
        mapping_args = {}

    def ffunc(entry):
        imagename = entry.get('imagename', '')
        if excludes:
            for p in excludes:
                if re.search(p, imagename):
                    return None
        if service_filter is not None:
            # check the entry is for a service being deployed
            image_services = set(entry.get('services', []))
            if not image_services.intersection(service_filter):
                return None
        return entry

    builder = KollaImageBuilder([template_file])
    result = builder.container_images_from_template(
        filter=ffunc, **mapping_args)

    if tag_from_label:
        uploader = image_uploader.ImageUploadManager().uploader('docker')
        images = [i.get('imagename', '') for i in result]
        image_version_tags = uploader.discover_image_tags(
            images, tag_from_label)
        for entry in result:
            imagename = entry.get('imagename', '')
            image_no_tag = imagename.rpartition(':')[0]
            if image_no_tag in image_version_tags:
                entry['imagename'] = '%s:%s' % (
                    image_no_tag, image_version_tags[image_no_tag])

    params = {}
    for entry in result:
        imagename = entry.get('imagename', '')
        if pull_source:
            entry['pull_source'] = pull_source
        if push_destination:
            entry['push_destination'] = push_destination
            # replace the host portion of the imagename with the
            # push_destination, since that is where they will be uploaded to
            image = imagename.partition('/')[2]
            imagename = '/'.join((push_destination, image))
        if 'params' in entry:
            for p in entry.pop('params'):
                params[p] = imagename
        if 'services' in entry:
            del(entry['services'])

    params.update(
        detect_insecure_registries(params))

    return_data = {}
    if output_env_file:
        return_data[output_env_file] = params
    if output_images_file:
        return_data[output_images_file] = result
    return return_data


def detect_insecure_registries(params):
    insecure = set()
    uploader = image_uploader.ImageUploadManager().uploader('docker')
    for image in params.values():
        host = image.split('/')[0]
        if uploader.is_insecure_registry(host):
            insecure.add(host)
    if not insecure:
        return {}
    return {'DockerInsecureRegistryAddress': sorted(insecure)}


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

    @staticmethod
    def container_images_template_inputs(**kwargs):
        '''Build the template mapping from defaults and keyword arguments.

        Defaults in CONTAINER_IMAGES_DEFAULTS are combined with keyword
        argments to return a dict that can be used to render the container
        images template. Any set values for name_prefix and name_suffix are
        hyphenated appropriately.
        '''
        mapping = dict(kwargs)
        for k, v in CONTAINER_IMAGES_DEFAULTS.items():
            mapping.setdefault(k, v)
        np = mapping['name_prefix']
        if np and not np.endswith('-'):
            mapping['name_prefix'] = np + '-'
        ns = mapping['name_suffix']
        if ns and not ns.startswith('-'):
            mapping['name_suffix'] = '-' + ns
        return mapping

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

        Defaults are applied so that when no arguments are provided.
        '''
        mapping = self.container_images_template_inputs(**kwargs)
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
