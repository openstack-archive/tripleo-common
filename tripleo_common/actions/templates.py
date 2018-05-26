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
import yaml

from heatclient import exc as heat_exc
from mistral_lib import actions
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import plan as plan_utils

LOG = logging.getLogger(__name__)


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


class UploadTemplatesAction(base.UploadDirectoryAction):
    """Upload default heat templates for TripleO."""
    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME,
                 dir_to_upload=constants.DEFAULT_TEMPLATES_PATH):
        super(UploadTemplatesAction, self).__init__(container, dir_to_upload)


class UploadPlanEnvironmentAction(base.TripleOAction):
    """Upload the plan environment into swift"""
    def __init__(self, plan_environment,
                 container=constants.DEFAULT_CONTAINER_NAME):
        super(UploadPlanEnvironmentAction, self).__init__()
        self.container = container
        self.plan_environment = plan_environment

    def run(self, context):
        # Get object client
        swift = self.get_object_client(context)
        # Push plan environment to the swift container
        plan_utils.put_env(swift, self.plan_environment)


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

    def _heat_resource_exists(self, nested_stack_name, resource_name, context):
        heatclient = self.get_orchestration_client(context)
        try:
            stack = heatclient.stacks.get(self.container)
        except heat_exc.HTTPNotFound:
            LOG.debug("Resource does not exist because stack does not exist")
            return False

        try:
            nested_stack = heatclient.resources.get(stack.id,
                                                    nested_stack_name)
        except heat_exc.HTTPNotFound:
            LOG.debug(
                "Resource does not exist because {} stack does "
                "not exist".format(nested_stack_name))
            return False

        try:
            heatclient.resources.get(nested_stack.physical_resource_id,
                                     resource_name)
        except heat_exc.HTTPNotFound:
            LOG.debug("Resource does not exist: {}".format(resource_name))
            return False
        else:
            LOG.debug("Resource exists: {}".format(resource_name))
            return True

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
            if n.get('enabled') is not False:
                n_map[n.get('name')] = n
                if not n.get('name_lower'):
                    n_map[n.get('name')]['name_lower'] = n.get('name').lower()
            if n.get('name') == constants.API_NETWORK and 'compat_name' \
                    not in n.keys():
                # Check to see if legacy named API network exists
                # and if so we need to set compat_name
                api_net = "{}Network".format(constants.LEGACY_API_NETWORK)
                if self._heat_resource_exists('Networks', api_net, context):
                    n['compat_name'] = 'Internal'
                    LOG.info("Upgrade compatibility enabled for legacy "
                             "network resource Internal.")
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

        template_name = plan_env.get('template', "")

        template_object = os.path.join(swift.url, self.container,
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
                swift, self.container, plan_env)
            env_files, env = plan_utils.process_environments_and_files(
                swift, env_paths)
        except Exception as err:
            error_text = six.text_type(err)
            LOG.exception("Error occurred while processing plan files.")
        finally:
            # cleanup any local temp files
            for f in temp_env_paths:
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
