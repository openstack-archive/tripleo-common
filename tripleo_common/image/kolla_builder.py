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
import os
import re
import subprocess
import sys
import tempfile
import time
import yaml

from osc_lib.i18n import _
from oslo_log import log as logging
from tripleo_common.image import base
from tripleo_common.image import image_uploader
from tripleo_common.utils.locks import threadinglock

CONTAINER_IMAGE_PREPARE_PARAM_STR = None

CONTAINER_IMAGE_PREPARE_PARAM = None

CONTAINER_IMAGES_DEFAULTS = None


def init_prepare_defaults(defaults_file):
    global CONTAINER_IMAGE_PREPARE_PARAM_STR
    with open(defaults_file) as f:
        CONTAINER_IMAGE_PREPARE_PARAM_STR = f.read()

    global CONTAINER_IMAGE_PREPARE_PARAM
    p = yaml.safe_load(CONTAINER_IMAGE_PREPARE_PARAM_STR)
    CONTAINER_IMAGE_PREPARE_PARAM = p[
        'parameter_defaults']['ContainerImagePrepare']

    global CONTAINER_IMAGES_DEFAULTS
    CONTAINER_IMAGES_DEFAULTS = CONTAINER_IMAGE_PREPARE_PARAM[0]['set']
    # Handle CentOS8 since we shipped train with py2 support, we need
    # to still support it while handling the namespace switch for
    # CentOS8 but only for the defaults
    if (CONTAINER_IMAGES_DEFAULTS['namespace'] == 'docker.io/tripleotrain'
            and sys.version_info.major > 2):
        CONTAINER_IMAGES_DEFAULTS['namespace'] += 'centos8'


DEFAULT_TEMPLATE_FILE = os.path.join(sys.prefix, 'share', 'tripleo-common',
                                     'container-images',
                                     'overcloud_containers.yaml.j2')

DEFAULT_PREPARE_FILE = os.path.join(sys.prefix, 'share', 'tripleo-common',
                                    'container-images',
                                    'container_image_prepare_defaults.yaml')

if os.path.isfile(DEFAULT_PREPARE_FILE):
    init_prepare_defaults(DEFAULT_PREPARE_FILE)

LOG = logging.getLogger(__name__ + '.KollaImageBuilder')


def get_enabled_services(environment, roles_data):
    """Build list of enabled services

    :param environment: Heat environment for deployment
    :param roles_data: Roles file data used to filter services
    :returns: set of resource types representing enabled services
    """
    enabled_services = set()
    parameter_defaults = environment.get('parameter_defaults', {})
    for role in roles_data:
        count = parameter_defaults.get('%sCount' % role['name'],
                                       role.get('CountDefault', 0))
        try:
            count = int(count)
        except ValueError:
            raise ValueError('Unable to convert %sCount to an int: %s' %
                             (role['name'], count))

        if count > 0:
            enabled_services.update(
                parameter_defaults.get('%sServices' % role['name'],
                                       role.get('ServicesDefault', [])))
    return enabled_services


def build_service_filter(environment, roles_data):
    """Build list of containerized services

    :param environment: Heat environment for deployment
    :param roles_data: Roles file data used to filter services
    :returns: set of resource types representing containerized services
    """
    if not roles_data:
        return None
    enabled_services = get_enabled_services(environment, roles_data)
    resource_registry = environment.get('resource_registry')
    if resource_registry:
        for service in enabled_services.copy():
            env_path = resource_registry.get(service)
            if env_path == 'OS::Heat::None':
                enabled_services.remove(service)

    return enabled_services


def set_neutron_driver(pd, mapping_args):
    """Set the neutron_driver images variable based on parameters

    :param pd: Parameter defaults from the environment
    :param mapping_args: Dict to set neutron_driver value on
    """
    if not pd or 'NeutronMechanismDrivers' not in pd:
        # we should set default neutron driver
        mapping_args['neutron_driver'] = 'ovn'
        return
    nmd = pd['NeutronMechanismDrivers']
    if 'opendaylight_v2' in nmd:
        mapping_args['neutron_driver'] = 'odl'
    elif 'ovn' in nmd:
        mapping_args['neutron_driver'] = 'ovn'
    else:
        mapping_args['neutron_driver'] = 'other'


def container_images_prepare_multi(environment, roles_data, dry_run=False,
                                   cleanup=image_uploader.CLEANUP_FULL,
                                   lock=None):
    """Perform multiple container image prepares and merge result

    Given the full heat environment and roles data, perform multiple image
    prepare operations. The data to drive the multiple prepares is taken from
    the ContainerImagePrepare parameter in the provided environment. If
    push_destination is specified, uploads will be performed during the
    preparation.

    :param environment: Heat environment for deployment
    :param roles_data: Roles file data used to filter services
    :param lock: a locking object to use when handling uploads
    :returns: dict containing merged container image parameters from all
              prepare operations
    """

    if not lock:
        lock = threadinglock.ThreadingLock()

    pd = environment.get('parameter_defaults', {})
    cip = pd.get('ContainerImagePrepare')
    # if user does not provide a ContainerImagePrepare, use the defaults.
    if not cip:
        LOG.info(_("No ContainerImagePrepare parameter defined. Using "
                   "the defaults."))
        cip = CONTAINER_IMAGE_PREPARE_PARAM

    mirrors = {}
    mirror = pd.get('DockerRegistryMirror')
    if mirror:
        mirrors['docker.io'] = mirror

    creds = pd.get('ContainerImageRegistryCredentials')
    multi_arch = len(pd.get('AdditionalArchitectures', []))

    env_params = {}
    service_filter = build_service_filter(environment, roles_data)

    for cip_entry in cip:
        mapping_args = cip_entry.get('set', {})
        set_neutron_driver(pd, mapping_args)
        push_destination = cip_entry.get('push_destination')
        # use the configured registry IP as the discovered registry
        # if it is available
        if push_destination and isinstance(push_destination, bool):
            local_registry_ip = pd.get('LocalContainerRegistry')
            if local_registry_ip:
                push_destination = '%s:8787' % local_registry_ip
        pull_source = cip_entry.get('pull_source')
        modify_role = cip_entry.get('modify_role')
        modify_vars = cip_entry.get('modify_vars')
        modify_only_with_labels = cip_entry.get('modify_only_with_labels')
        modify_only_with_source = cip_entry.get('modify_only_with_source')
        modify_append_tag = cip_entry.get('modify_append_tag',
                                          time.strftime(
                                              '-modified-%Y%m%d%H%M%S'))

        # do not use tag_from_label if a tag is specified in the set
        tag_from_label = None
        if not mapping_args.get('tag'):
            tag_from_label = cip_entry.get('tag_from_label')

        if multi_arch and 'multi_arch' in cip_entry:
            # individual entry sets multi_arch,
            # so set global multi_arch to False
            multi_arch = False

        prepare_data = container_images_prepare(
            excludes=cip_entry.get('excludes'),
            includes=cip_entry.get('includes'),
            service_filter=service_filter,
            pull_source=pull_source,
            push_destination=push_destination,
            mapping_args=mapping_args,
            output_env_file='image_params',
            output_images_file='upload_data',
            tag_from_label=tag_from_label,
            append_tag=modify_append_tag,
            modify_role=modify_role,
            modify_vars=modify_vars,
            modify_only_with_labels=modify_only_with_labels,
            modify_only_with_source=modify_only_with_source,
            mirrors=mirrors,
            registry_credentials=creds,
            multi_arch=multi_arch,
            lock=lock
        )
        env_params.update(prepare_data['image_params'])

        if not dry_run and (push_destination or pull_source or modify_role):
            with tempfile.NamedTemporaryFile(mode='w') as f:
                yaml.safe_dump({
                    'container_images': prepare_data['upload_data']
                }, f)
                uploader = image_uploader.ImageUploadManager(
                    [f.name],
                    cleanup=cleanup,
                    mirrors=mirrors,
                    registry_credentials=creds,
                    multi_arch=multi_arch,
                    lock=lock
                )
                uploader.upload()
    return env_params


def container_images_prepare_defaults():
    """Return default dict for prepare substitutions

    This can be used as the mapping_args argument to the
    container_images_prepare function to get the same result as not specifying
    any mapping_args.
    """
    return KollaImageBuilder.container_images_template_inputs()


def container_images_prepare(template_file=DEFAULT_TEMPLATE_FILE,
                             excludes=None, includes=None, service_filter=None,
                             pull_source=None, push_destination=None,
                             mapping_args=None, output_env_file=None,
                             output_images_file=None, tag_from_label=None,
                             append_tag=None, modify_role=None,
                             modify_vars=None, modify_only_with_labels=None,
                             modify_only_with_source=None,
                             mirrors=None, registry_credentials=None,
                             multi_arch=False, lock=None):
    """Perform container image preparation

    :param template_file: path to Jinja2 file containing all image entries
    :param excludes: list of image name substrings to use for exclude filter
    :param includes: list of image name substrings, at least one must match.
                     All excludes are ignored if includes is specified.
    :param service_filter: set of heat resource types for containerized
                           services to filter by. Disable by passing None.
    :param pull_source: DEPRECATED namespace for pulling during image uploads
    :param push_destination: namespace for pushing during image uploads. When
                             specified the image parameters will use this
                             namespace too.
    :param mapping_args: dict containing substitutions for template file. See
                         CONTAINER_IMAGES_DEFAULTS for expected keys.
    :param output_env_file: key to use for heat environment parameter data
    :param output_images_file: key to use for image upload data
    :param tag_from_label: string when set will trigger tag discovery on every
                           image
    :param append_tag: string to append to the tag for the destination
                              image
    :param modify_role: string of ansible role name to run during upload before
                        the push to destination
    :param modify_vars: dict of variables to pass to modify_role
    :param modify_only_with_labels: only modify the container images with the
                                    given labels
    :param modify_only_with_source: only modify the container images from a
                                    image_source in the tripleo-common service
                                    to container mapping (e.g. kolla/tripleo)
    :param mirrors: dict of registry netloc values to mirror urls
    :param registry_credentials: dict of registry netloc values to
                                 authentication credentials for that registry.
                                 The value is a single-entry dict where the
                                 username is the key and the password is the
                                 value.
    :param multi_arch: boolean whether to prepare every architecture of
                       each image

    :param lock: a locking object to use when handling uploads
    :returns: dict with entries for the supplied output_env_file or
              output_images_file
    """

    if mapping_args is None:
        mapping_args = {}

    if not lock:
        lock = threadinglock.ThreadingLock()

    def ffunc(entry):
        imagename = entry.get('imagename', '')
        if service_filter is not None:
            # check the entry is for a service being deployed
            image_services = set(entry.get('services', []))
            if not image_services.intersection(service_filter):
                return None
        if includes:
            for p in includes:
                if re.search(p, imagename):
                    return entry
            return None
        if excludes:
            for p in excludes:
                if re.search(p, imagename):
                    return None
        return entry

    builder = KollaImageBuilder([template_file])
    result = builder.container_images_from_template(
        filter=ffunc, **mapping_args)

    manager = image_uploader.ImageUploadManager(
        mirrors=mirrors,
        registry_credentials=registry_credentials,
        multi_arch=multi_arch,
        lock=lock
    )
    uploader = manager.uploader('python')
    images = [i.get('imagename', '') for i in result]
    if result:
        default_tag = result[0].get('default_tag', False)
    else:
        default_tag = False

    if tag_from_label:
        image_version_tags = uploader.discover_image_tags(
            images, tag_from_label, default_tag)
        for entry in result:
            imagename = entry.get('imagename', '')
            image_no_tag = imagename.rpartition(':')[0]
            if image_no_tag in image_version_tags:
                entry['imagename'] = '%s:%s' % (
                    image_no_tag, image_version_tags[image_no_tag])

    images_with_labels = []
    if modify_only_with_labels:
        images_with_labels = uploader.filter_images_with_labels(
            images, modify_only_with_labels)

    images_with_source = []
    if modify_only_with_source:
        images_with_source = [i.get('imagename') for i in result
                              if i.get('image_source', '')
                              in modify_only_with_source]

    params = {}
    modify_append_tag = append_tag
    for entry in result:
        imagename = entry.get('imagename', '')
        append_tag = ''
        if modify_role and (
                (not modify_only_with_labels
                    and not modify_only_with_source) or
                (imagename in images_with_labels or
                    imagename in images_with_source)):
            entry['modify_role'] = modify_role
            if modify_append_tag:
                entry['modify_append_tag'] = modify_append_tag
                append_tag = modify_append_tag
            if modify_vars:
                entry['modify_vars'] = modify_vars
        if pull_source:
            entry['pull_source'] = pull_source
        if push_destination:
            # substitute discovered registry if push_destination is set to true
            if isinstance(push_destination, bool):
                push_destination = image_uploader.get_undercloud_registry()

            entry['push_destination'] = push_destination
            # replace the host portion of the imagename with the
            # push_destination, since that is where they will be uploaded to
            image = imagename.partition('/')[2]
            imagename = '/'.join((push_destination, image))
        if 'params' in entry:
            for p in entry.pop('params'):
                params[p] = imagename + append_tag
        if 'services' in entry:
            del(entry['services'])

    params.update(
        detect_insecure_registries(params, lock=lock))

    return_data = {}
    if output_env_file:
        return_data[output_env_file] = params
    if output_images_file:
        return_data[output_images_file] = result
    return return_data


def detect_insecure_registries(params, lock=None):
    """Detect insecure registries in image parameters

    :param params: dict of container image parameters
    :returns: dict containing DockerInsecureRegistryAddress parameter to be
              merged into other parameters
    """
    insecure = set()
    uploader = image_uploader.ImageUploadManager(lock=lock).uploader('python')
    for image in params.values():
        host = image.split('/')[0]
        if uploader.is_insecure_registry(host):
            insecure.add(host)
    if not insecure:
        return {}
    return {'DockerInsecureRegistryAddress': sorted(insecure)}


class KollaImageBuilder(base.BaseImageManager):
    """Build images using kolla-build"""

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
        # set a flag to record whether the default tag is used or not. the
        # logic here is that if the tag key is not already in mapping then it
        # wil be added during the template render, so default_tag is set to
        # True.
        mapping['default_tag'] = 'tag' not in mapping

        if CONTAINER_IMAGES_DEFAULTS is None:
            return
        for k, v in CONTAINER_IMAGES_DEFAULTS.items():
            # Handle CentOS8 since we shipped train with py2 support, we need
            # to still support it while handling the namespace switch for
            # CentOS8 but only for the defaults
            if (k == 'namespace' and v == 'docker.io/tripleotrain'
                    and sys.version_info.major > 2):
                v += 'centos8'
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

    def build_images(self, kolla_config_files=None, excludes=[],
                     template_only=False, kolla_tmp_dir=None):

        cmd = ['kolla-build']
        if kolla_config_files:
            for f in kolla_config_files:
                cmd.append('--config-file')
                cmd.append(f)

        if len(self.config_files) == 0:
            self.config_files = [DEFAULT_TEMPLATE_FILE]
            container_images = self.container_images_from_template()
        else:
            container_images = self.load_config_files(self.CONTAINER_IMAGES) \
                or []
        container_images.sort(key=lambda i: i.get('imagename'))
        for i in container_images:
            # Do not attempt to build containers that are not from kolla or
            # are in our exclude list
            if not i.get('image_source', '') == 'kolla':
                continue
            image = self.imagename_to_regex(i.get('imagename'))
            # Make sure the image was properly parsed and not purposely skipped
            if image and image not in excludes:
                # NOTE(mgoddard): Use a full string match.
                cmd.append("^%s$" % image)

        if template_only:
            # build the dep list cmd line
            cmd_deps = list(cmd)
            cmd_deps.append('--list-dependencies')
            # build the template only cmd line
            cmd.append('--template-only')
            cmd.append('--work-dir')
            cmd.append(kolla_tmp_dir)

        LOG.info(_('Running %s'), ' '.join(cmd))
        env = os.environ.copy()
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                   universal_newlines=True)
        out, err = process.communicate()
        if process.returncode != 0:
            LOG.error(_('Building containers image process failed with %d rc'),
                      process.returncode)
            raise subprocess.CalledProcessError(process.returncode, cmd, err)

        if template_only:
            self.logger.info('Running %s' % ' '.join(cmd_deps))
            env = os.environ.copy()
            process = subprocess.Popen(cmd_deps, env=env,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       universal_newlines=True)
            out, err = process.communicate()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode,
                                                    cmd_deps, err)
        return out
