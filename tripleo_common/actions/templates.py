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
import json
import logging
import os
import requests
import six
import tempfile as tf
import yaml

from heatclient.common import template_utils
from mistral_lib import actions
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import tarball

LOG = logging.getLogger(__name__)


def _create_temp_file(data):
    handle, env_temp_file = tf.mkstemp()
    with open(env_temp_file, 'w') as temp_file:
        temp_file.write(json.dumps(data))
        os.close(handle)
    return env_temp_file


class J2SwiftLoader(jinja2.BaseLoader):
    """Jinja2 loader to fetch included files from swift

    This attempts to fetch a template include file from the given container.
    An optional search path or list of search paths can be provided. By default
    only the absolute path relative to the container root is searched.
    """

    def __init__(self, swift, container, searchpath=None):
        self.swift = swift
        self.container = container
        if searchpath is not None:
            if isinstance(searchpath, six.string_types):
                self.searchpath = [searchpath]
            else:
                self.searchpath = list(searchpath)
        else:
            self.searchpath = []
        # Always search the absolute path from the root of the swift container
        if '' not in self.searchpath:
            self.searchpath.append('')

    def get_source(self, environment, template):
        pieces = jinja2.loaders.split_template_path(template)
        for searchpath in self.searchpath:
            template_path = os.path.join(searchpath, *pieces)
            try:
                source = self.swift.get_object(
                    self.container, template_path)[1]
                return source, None, False
            except swiftexceptions.ClientException:
                pass
        raise jinja2.exceptions.TemplateNotFound(template)


class UploadTemplatesAction(base.TripleOAction):
    """Upload default heat templates for TripleO."""
    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME,
                 templates_path=constants.DEFAULT_TEMPLATES_PATH):
        super(UploadTemplatesAction, self).__init__()
        self.container = container
        self.templates_path = templates_path

    def run(self, context):
        with tf.NamedTemporaryFile() as tmp_tarball:
            tarball.create_tarball(self.templates_path, tmp_tarball.name)
            tarball.tarball_extract_to_swift_container(
                self.get_object_client(context),
                tmp_tarball.name,
                self.container)


class ProcessTemplatesAction(base.TripleOAction):
    """Process Templates and Environments

    This method processes the templates and files in a given deployment
    plan into a format that can be passed to Heat.
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(ProcessTemplatesAction, self).__init__()
        self.container = container

    def _j2_render_and_put(self,
                           j2_template,
                           j2_data,
                           outfile_name=None,
                           context=None):
        swift = self.get_object_client(context)
        yaml_f = outfile_name or j2_template.replace('.j2.yaml', '.yaml')

        # Search for templates relative to the current template path first
        template_base = os.path.dirname(yaml_f)
        j2_loader = J2SwiftLoader(swift, self.container, template_base)

        try:
            # Render the j2 template
            template = jinja2.Environment(loader=j2_loader).from_string(
                j2_template)
            r_template = template.render(**j2_data)
        except jinja2.exceptions.TemplateError as ex:
            error_msg = ("Error rendering template %s : %s"
                         % (yaml_f, six.text_type(ex)))
            LOG.error(error_msg)
            raise Exception(error_msg)
        try:
            # write the template back to the plan container
            LOG.info("Writing rendered template %s" % yaml_f)
            self.cache_delete(context,
                              self.container,
                              "tripleo.parameters.get")
            swift.put_object(
                self.container, yaml_f, r_template)
        except swiftexceptions.ClientException as ex:
            error_msg = ("Error storing file %s in container %s"
                         % (yaml_f, self.container))
            LOG.error(error_msg)
            raise Exception(error_msg)

    def _get_j2_excludes_file(self, context):
        swift = self.get_object_client(context)
        try:
            j2_excl_file = swift.get_object(
                self.container, constants.OVERCLOUD_J2_EXCLUDES)[1]
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

    def _process_custom_roles(self, context):
        swift = self.get_object_client(context)

        try:
            j2_role_file = swift.get_object(
                self.container, constants.OVERCLOUD_J2_ROLES_NAME)[1]
            role_data = yaml.safe_load(j2_role_file)
        except swiftexceptions.ClientException:
            LOG.info("No %s file found, skipping jinja templating"
                     % constants.OVERCLOUD_J2_ROLES_NAME)
            return

        try:
            j2_network_file = swift.get_object(
                self.container, constants.OVERCLOUD_J2_NETWORKS_NAME)[1]
            network_data = yaml.safe_load(j2_network_file)
        except swiftexceptions.ClientException:
            # Until t-h-t contains network_data.yaml we tolerate a missing file
            LOG.warning("No %s file found, ignoring"
                        % constants.OVERCLOUD_J2_ROLES_NAME)
            network_data = []

        j2_excl_data = self._get_j2_excludes_file(context)

        try:
            # Iterate over all files in the plan container
            # we j2 render any with the .j2.yaml suffix
            container_files = swift.get_container(self.container)
        except swiftexceptions.ClientException as ex:
            error_msg = ("Error listing contents of container %s : %s"
                         % (self.container, six.text_type(ex)))
            LOG.error(error_msg)
            raise Exception(error_msg)

        role_names = [r.get('name') for r in role_data]
        r_map = {}
        for r in role_data:
            r_map[r.get('name')] = r
        excl_templates = j2_excl_data.get('name')

        n_map = {}
        for n in network_data:
            if (n.get('enabled') is not False):
                n_map[n.get('name')] = n
                if not n.get('name_lower'):
                    n_map[n.get('name')]['name_lower'] = n.get('name').lower()
            else:
                LOG.info("skipping %s network: network is disabled." %
                         n.get('name'))

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
                j2_template = swift.get_object(self.container, f)[1]
                LOG.info("jinja2 rendering roles %s" % ","
                         .join(role_names))
                for role in role_names:
                    LOG.info("jinja2 rendering role %s" % role)
                    out_f = "-".join(
                        [role.lower(),
                         os.path.basename(f).replace('.role.j2.yaml',
                                                     '.yaml')])
                    out_f_path = os.path.join(os.path.dirname(f), out_f)
                    if not (out_f_path in excl_templates):
                        if '{{role.name}}' in j2_template:
                            j2_data = {'role': r_map[role],
                                       'networks': network_data}
                            self._j2_render_and_put(j2_template,
                                                    j2_data,
                                                    out_f_path,
                                                    context=context)
                        else:
                            # Backwards compatibility with templates
                            # that specify {{role}} vs {{role.name}}
                            j2_data = {'role': role, 'networks': network_data}
                            LOG.debug("role legacy path for role %s" % role)
                            if r_map[role].get('disable_constraints', False):
                                j2_data['disable_constraints'] = True
                            self._j2_render_and_put(j2_template,
                                                    j2_data,
                                                    out_f_path,
                                                    context=context)
                    else:
                        LOG.info("Skipping rendering of %s, defined in %s" %
                                 (out_f_path, j2_excl_data))

            elif (f.endswith('.network.j2.yaml')):
                LOG.info("jinja2 rendering network template %s" % f)
                j2_template = swift.get_object(self.container, f)[1]
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
                        self._j2_render_and_put(j2_template,
                                                j2_data,
                                                out_f_path,
                                                context=context)
                    else:
                        LOG.info("Skipping rendering of %s, defined in %s" %
                                 (out_f_path, j2_excl_data))

            elif f.endswith('.j2.yaml'):
                LOG.info("jinja2 rendering %s" % f)
                j2_template = swift.get_object(self.container, f)[1]
                j2_data = {'roles': role_data, 'networks': network_data}
                out_f = f.replace('.j2.yaml', '.yaml')
                self._j2_render_and_put(j2_template,
                                        j2_data,
                                        out_f,
                                        context=context)

    def run(self, context):
        error_text = None
        self.context = context
        swift = self.get_object_client(context)

        try:
            plan_env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=error_text)

        try:
            # if the jinja overcloud template exists, process it and write it
            # back to the swift container before continuing processing.  The
            # method called below should handle the case where the files are
            # not found in swift, but if they are found and an exception
            # occurs during processing, that exception will cause the
            # ProcessTemplatesAction to return an error result.
            self._process_custom_roles(context)
        except Exception as err:
            LOG.exception("Error occurred while processing custom roles.")
            return actions.Result(error=six.text_type(err))

        template_name = plan_env.get('template')
        environments = plan_env.get('environments')
        env_paths = []
        temp_files = []

        template_object = os.path.join(swift.url, self.container,
                                       template_name)

        LOG.debug('Template: %s' % template_name)
        LOG.debug('Environments: %s' % environments)
        try:
            for env in environments:
                if env.get('path'):
                    env_paths.append(os.path.join(swift.url, self.container,
                                                  env['path']))
                elif env.get('data'):
                    env_temp_file = _create_temp_file(env['data'])
                    temp_files.append(env_temp_file)
                    env_paths.append(env_temp_file)

            # create a dict to hold all user set params and merge
            # them in the appropriate order
            merged_params = {}
            # merge generated passwords into params first
            passwords = plan_env.get('passwords', {})
            merged_params.update(passwords)

            # derived parameters are merged before 'parameter defaults'
            # so that user-specified values can override the derived values.
            derived_params = plan_env.get('derived_parameters', {})
            merged_params.update(derived_params)

            # handle user set parameter values next in case a user has set
            # a new value for a password parameter
            params = plan_env.get('parameter_defaults', {})
            merged_params = template_utils.deep_update(merged_params, params)

            if merged_params:
                env_temp_file = _create_temp_file(
                    {'parameter_defaults': merged_params})
                temp_files.append(env_temp_file)
                env_paths.append(env_temp_file)

            registry = plan_env.get('resource_registry', {})
            if registry:
                env_temp_file = _create_temp_file(
                    {'resource_registry': registry})
                temp_files.append(env_temp_file)
                env_paths.append(env_temp_file)

            def _env_path_is_object(env_path):
                retval = env_path.startswith(swift.url)
                LOG.debug('_env_path_is_object %s: %s' % (env_path, retval))
                return retval

            def _object_request(method, url, token=context.auth_token):
                response = requests.request(
                    method, url, headers={'X-Auth-Token': token})
                response.raise_for_status()
                return response.content

            template_files, template = template_utils.get_template_contents(
                template_object=template_object,
                object_request=_object_request)

            env_files, env = (
                template_utils.process_multiple_environments_and_files(
                    env_paths=env_paths,
                    env_path_is_object=_env_path_is_object,
                    object_request=_object_request))

        except Exception as err:
            error_text = six.text_type(err)
            LOG.exception("Error occurred while processing plan files.")
        finally:
            # cleanup any local temp files
            for f in temp_files:
                os.remove(f)

        if error_text:
            return actions.Result(error=error_text)

        files = dict(list(template_files.items()) + list(env_files.items()))

        return {
            'stack_name': self.container,
            'template': template,
            'environment': env,
            'files': files
        }
