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
import jinja2
import logging
import os
import six
import tempfile
import yaml

from heatclient import exc as heat_exc
from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
from tripleo_common.utils import parameters
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import swift as swiftutils
from tripleo_common.utils import tarball

LOG = logging.getLogger(__name__)


class J2SwiftLoader(jinja2.BaseLoader):
    """Jinja2 loader to fetch included files from swift

    This attempts to fetch a template include file from the given container.
    An optional search path or list of search paths can be provided. By default
    only the absolute path relative to the container root is searched.
    """

    def __init__(self, swift, container, searchpath):
        self.swift = swift
        self.container = container
        self.searchpath = [searchpath]
        # Always search the absolute path from the root of the swift container
        if '' not in self.searchpath:
            self.searchpath.append('')

    def get_source(self, environment, template):
        pieces = jinja2.loaders.split_template_path(template)
        for searchpath in self.searchpath:
            template_path = os.path.join(searchpath, *pieces)
            try:
                source = swiftutils.get_object_string(self.swift,
                                                      self.container,
                                                      template_path)
                return source, None, False
            except swiftexceptions.ClientException:
                pass
        raise jinja2.exceptions.TemplateNotFound(template)


def j2_render_and_put(swift, j2_template, j2_data, yaml_f,
                      container=constants.DEFAULT_CONTAINER_NAME):

    def raise_helper(msg):
        raise jinja2.exceptions.TemplateError(msg)

    # Search for templates relative to the current template path first
    template_base = os.path.dirname(yaml_f)
    j2_loader = J2SwiftLoader(swift, container, template_base)

    try:
        # Render the j2 template
        jinja2_env = jinja2.Environment(loader=j2_loader)
        jinja2_env.globals['raise'] = raise_helper
        template = jinja2_env.from_string(j2_template)
        r_template = template.render(**j2_data)
    except jinja2.exceptions.TemplateError as ex:
        error_msg = ("Error rendering template %s : %s"
                     % (yaml_f, six.text_type(ex)))
        LOG.error(error_msg)
        raise RuntimeError(error_msg)

    try:
        # write the template back to the plan container
        LOG.info("Writing rendered template %s" % yaml_f)
        swiftutils.put_object_string(swift, container, yaml_f,
                                     r_template)
    except swiftexceptions.ClientException:
        error_msg = ("Error storing file %s in container %s"
                     % (yaml_f, container))
        LOG.error(error_msg)
        raise RuntimeError(error_msg)


def get_j2_excludes_file(swift, container=constants.DEFAULT_CONTAINER_NAME):
    try:
        j2_excl_file = swiftutils.get_object_string(
            swift, container, constants.OVERCLOUD_J2_EXCLUDES)
        j2_excl_data = yaml.safe_load(j2_excl_file)
        if (j2_excl_data is None or j2_excl_data.get('name') is None):
            j2_excl_data = {"name": []}
            LOG.info("j2_excludes.yaml is either empty or there are "
                     "no templates to exclude, defaulting the J2 "
                     "excludes list to: %s" % j2_excl_data)
    except swiftexceptions.ClientException:
        j2_excl_data = {"name": []}
        LOG.info("No J2 exclude file found, defaulting "
                 "the J2 excludes list to: %s" % j2_excl_data)
    return j2_excl_data


def heat_resource_exists(heat, stack, nested_stack_name, resource_name):
    if stack is None:
        LOG.debug("Resource does not exist because stack does not exist")
        return False

    try:
        nested_stack = heat.resources.get(stack.id, nested_stack_name)
    except heat_exc.HTTPNotFound:
        LOG.debug(
            "Resource does not exist because {} stack does "
            "not exist".format(nested_stack_name))
        return False

    try:
        heat.resources.get(nested_stack.physical_resource_id,
                           resource_name)
    except heat_exc.HTTPNotFound:
        LOG.debug("Resource does not exist: {}".format(resource_name))
        return False
    else:
        LOG.debug("Resource exists: {}".format(resource_name))
        return True


def process_custom_roles(swift, heat,
                         container=constants.DEFAULT_CONTAINER_NAME):
    try:
        j2_role_file = swiftutils.get_object_string(
            swift, container, constants.OVERCLOUD_J2_ROLES_NAME)
        role_data = yaml.safe_load(j2_role_file)
    except swiftexceptions.ClientException:
        LOG.info("No %s file found, skipping jinja templating"
                 % constants.OVERCLOUD_J2_ROLES_NAME)
        return

    try:
        j2_network_file = swiftutils.get_object_string(
            swift, container, constants.OVERCLOUD_J2_NETWORKS_NAME)
        network_data = yaml.safe_load(j2_network_file)
        # Allow no networks defined in network_data
        if network_data is None:
            network_data = []
        # Set internal network index key for each network, network resources
        # are created with a tag tripleo_net_idx
        for idx, _ in enumerate(network_data):
            network_data[idx].update({'idx': idx})
    except swiftexceptions.ClientException:
        # Until t-h-t contains network_data.yaml we tolerate a missing file
        LOG.warning("No %s file found, ignoring"
                    % constants.OVERCLOUD_J2_ROLES_NAME)
        network_data = []

    j2_excl_data = get_j2_excludes_file(swift, container)

    try:
        # Iterate over all files in the plan container
        # we j2 render any with the .j2.yaml suffix
        container_files = swift.get_container(container)
    except swiftexceptions.ClientException as ex:
        error_msg = ("Error listing contents of container %s : %s"
                     % (container, six.text_type(ex)))
        LOG.error(error_msg)
        raise RuntimeError(error_msg)

    role_names = [r.get('name') for r in role_data]
    r_map = {}
    for r in role_data:
        r_map[r.get('name')] = r
    excl_templates = j2_excl_data.get('name')

    stack = None
    try:
        stack = heat.stacks.get(container, resolve_outputs=False)
    except heat_exc.HTTPNotFound:
        LOG.debug("Stack does not exist")

    n_map = {}
    for n in network_data:
        if n.get('enabled') is not False:
            n_map[n.get('name')] = n
            if not n.get('name_lower'):
                n_map[n.get('name')]['name_lower'] = n.get('name').lower()
        if n.get('name') == constants.API_NETWORK and 'compat_name' \
                not in n.keys():
            # Check to see if legacy named API network exists
            # and if so we need to set compat_name
            api_net = "{}Network".format(constants.LEGACY_API_NETWORK)
            if heat_resource_exists(heat, stack, 'Networks', api_net):
                n['compat_name'] = 'Internal'
                LOG.info("Upgrade compatibility enabled for legacy "
                         "network resource Internal.")
        else:
            LOG.info("skipping %s network: network is disabled." %
                     n.get('name'))

    plan_utils.cache_delete(swift, container, "tripleo.parameters.get")

    for f in [f.get('name') for f in container_files[1]]:
        # We do three templating passes here:
        # 1. *.role.j2.yaml - we template just the role name
        #    and create multiple files (one per role)
        # 2  *.network.j2.yaml - we template the network name and
        #    data and create multiple files for networks and
        #    network ports (one per network)
        # 3. *.j2.yaml - we template with all roles_data,
        #    and create one file common to all roles
        if f.endswith('.role.j2.yaml'):
            LOG.info("jinja2 rendering role template %s" % f)
            j2_template = swiftutils.get_object_string(swift,
                                                       container, f)
            LOG.info("jinja2 rendering roles %s" % ","
                     .join(role_names))
            for role in role_names:
                LOG.info("jinja2 rendering role %s" % role)
                out_f = "-".join(
                    [role.lower(),
                     os.path.basename(f).replace('.role.j2.yaml',
                                                 '.yaml')])
                out_f_path = os.path.join(os.path.dirname(f), out_f)
                if ('network/config' in os.path.dirname(f) and
                        r_map[role].get('deprecated_nic_config_name')):
                    d_name = r_map[role].get('deprecated_nic_config_name')
                    out_f_path = os.path.join(os.path.dirname(f), d_name)
                elif ('network/config' in os.path.dirname(f)):
                    d_name = "%s.yaml" % role.lower()
                    out_f_path = os.path.join(os.path.dirname(f), d_name)
                if not (out_f_path in excl_templates):
                    if '{{role.name}}' in j2_template:
                        j2_data = {'role': r_map[role],
                                   'networks': network_data}
                        j2_render_and_put(swift, j2_template,
                                          j2_data, out_f_path,
                                          container)
                    else:
                        # Backwards compatibility with templates
                        # that specify {{role}} vs {{role.name}}
                        j2_data = {'role': role, 'networks': network_data}
                        LOG.debug("role legacy path for role %s" % role)
                        j2_render_and_put(swift, j2_template,
                                          j2_data, out_f_path,
                                          container)
                else:
                    LOG.info("Skipping rendering of %s, defined in %s" %
                             (out_f_path, j2_excl_data))

        elif (f.endswith('.network.j2.yaml')):
            LOG.info("jinja2 rendering network template %s" % f)
            j2_template = swiftutils.get_object_string(swift,
                                                       container,
                                                       f)
            LOG.info("jinja2 rendering networks %s" % ",".join(n_map))
            for network in n_map:
                j2_data = {'network': n_map[network]}
                # Output file names in "<name>.yaml" format
                out_f = os.path.basename(f).replace('.network.j2.yaml',
                                                    '.yaml')
                if os.path.dirname(f).endswith('ports'):
                    out_f = out_f.replace('port',
                                          n_map[network]['name_lower'])
                else:
                    out_f = out_f.replace('network',
                                          n_map[network]['name_lower'])
                out_f_path = os.path.join(os.path.dirname(f), out_f)
                if not (out_f_path in excl_templates):
                    j2_render_and_put(swift, j2_template,
                                      j2_data, out_f_path,
                                      container)
                else:
                    LOG.info("Skipping rendering of %s, defined in %s" %
                             (out_f_path, j2_excl_data))

        elif f.endswith('.j2.yaml'):
            LOG.info("jinja2 rendering %s" % f)
            j2_template = swiftutils.get_object_string(swift,
                                                       container,
                                                       f)
            j2_data = {'roles': role_data, 'networks': network_data}
            out_f = f.replace('.j2.yaml', '.yaml')
            j2_render_and_put(swift, j2_template,
                              j2_data, out_f,
                              container)
    return role_data


def prune_unused_services(swift, role_data,
                          resource_registry,
                          container=constants.DEFAULT_CONTAINER_NAME):
    """Remove unused services from role data

    Finds the unused services in the resource registry and removes them
    from the role data in the plan so we do not create OS::Heat::None
    resources.

    :param resource_registry: tripleo resource registry dict
    :param swift: swift client
    :param resource_registry: tripleo resource registry dict
    :returns: true if we updated the roles file. else false
    """
    to_remove = set()
    for key, value in resource_registry.items():
        if (key.startswith('OS::TripleO::Services::') and
                value.startswith('OS::Heat::None')):
            to_remove.add(key)

    if not to_remove or not role_data:
        LOG.info('No unused services to prune or no role data')
        return False

    LOG.info('Removing unused services from role data')
    for role in role_data:
        role_name = role.get('name')
        for service in to_remove:
            try:
                role.get('ServicesDefault', []).remove(service)
                LOG.debug('Removing {} from {} role'.format(
                    service, role_name))
            except ValueError:
                pass
    LOG.debug('Saving updated role data to swift')
    swift.put_object(container,
                     constants.OVERCLOUD_J2_ROLES_NAME,
                     yaml.safe_dump(role_data,
                                    default_flow_style=False))
    return True


def build_heat_args(swift, heat, container=constants.DEFAULT_CONTAINER_NAME):
    error_text = None
    try:
        plan_env = plan_utils.get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(error_text)

    try:
        # if the jinja overcloud template exists, process it and write it
        # back to the swift container before continuing processing.  The
        # method called below should handle the case where the files are
        # not found in swift, but if they are found and an exception
        # occurs during processing, then it will be raised.
        role_data = process_custom_roles(swift, heat, container)
    except Exception as err:
        LOG.exception("Error occurred while processing custom roles.")
        raise RuntimeError(six.text_type(err))

    template_name = plan_env.get('template', "")

    template_object = os.path.join(swift.url, container,
                                   template_name)
    LOG.debug('Template: %s' % template_name)
    try:
        template_files, template = plan_utils.get_template_contents(
            swift, template_object)
    except Exception as err:
        error_text = six.text_type(err)
        LOG.exception("Error occurred while fetching %s" % template_object)

    temp_env_paths = []
    try:
        env_paths, temp_env_paths = plan_utils.build_env_paths(
            swift, container, plan_env)
        env_files, env = plan_utils.process_environments_and_files(
            swift, env_paths)
        parameters.convert_docker_params(env)

    except Exception as err:
        error_text = six.text_type(err)
        LOG.exception("Error occurred while processing plan files.")
    finally:
        # cleanup any local temp files
        for f in temp_env_paths:
            os.remove(f)
    if error_text:
        raise RuntimeError(six.text_type(error_text))

    heat_args = {
        'template': template,
        'template_files': template_files,
        'env': env,
        'env_files': env_files
    }
    return heat_args, role_data


def process_templates(swift, heat, container=constants.DEFAULT_CONTAINER_NAME,
                      prune_services=False):
    heat_args, role_data = build_heat_args(swift, heat, container)
    if prune_services:
        try:
            # Prune OS::Heat::None resources
            resource_reg = heat_args['env'].get('resource_registry', {})
            roles_updated = prune_unused_services(
                swift, role_data, resource_reg, container)
            if roles_updated:
                heat_args, _ = build_heat_args(swift, heat, container)

        except Exception as err:
            LOG.exception("Error occurred while prunning prune_services.")
            raise RuntimeError(six.text_type(err))

    files = dict(list(heat_args['template_files'].items()) + list(
        heat_args['env_files'].items()))

    return {
        'stack_name': container,
        'template': heat_args['template'],
        'environment': heat_args['env'],
        'files': files
    }


def upload_templates_as_tarball(
    swift, dir_to_upload=constants.DEFAULT_TEMPLATES_PATH,
    container=constants.DEFAULT_CONTAINER_NAME):
    with tempfile.NamedTemporaryFile() as tmp_tarball:
        tarball.create_tarball(dir_to_upload, tmp_tarball.name)
        tarball.tarball_extract_to_swift_container(
            swift,
            tmp_tarball.name,
            container)
