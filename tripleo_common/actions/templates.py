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
from mistral import context
from mistral.workflow import utils as mistral_workflow_utils
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import tarball

LOG = logging.getLogger(__name__)


def _create_temp_file(data):
    handle, env_temp_file = tf.mkstemp()
    with open(env_temp_file, 'w') as temp_file:
        temp_file.write(json.dumps(data))
        os.close(handle)
    return env_temp_file


class UploadTemplatesAction(base.TripleOAction):
    """Upload default heat templates for TripleO."""
    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(UploadTemplatesAction, self).__init__()
        self.container = container

    def run(self):
        tht_base_path = constants.DEFAULT_TEMPLATES_PATH
        with tf.NamedTemporaryFile() as tmp_tarball:
            tarball.create_tarball(tht_base_path, tmp_tarball.name)
            tarball.tarball_extract_to_swift_container(
                self._get_object_client(),
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

    def _j2_render_and_put(self, j2_template, j2_data, outfile_name=None):
        swift = self._get_object_client()
        yaml_f = outfile_name or j2_template.replace('.j2.yaml', '.yaml')

        try:
            # Render the j2 template
            template = jinja2.Environment().from_string(j2_template)
            r_template = template.render(**j2_data)
        except jinja2.exceptions.TemplateError as ex:
            error_msg = ("Error rendering template %s : %s"
                         % (yaml_f, six.text_type(ex)))
            LOG.error(error_msg)
            raise Exception(error_msg)
        try:
            # write the template back to the plan container
            LOG.info("Writing rendered template %s" % yaml_f)
            swift.put_object(
                self.container, yaml_f, r_template)
        except swiftexceptions.ClientException as ex:
            error_msg = ("Error storing file %s in container %s"
                         % (yaml_f, self.container))
            LOG.error(error_msg)
            raise Exception(error_msg)

    def _get_j2_excludes_file(self):
        swift = self._get_object_client()
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

    def _process_custom_roles(self):
        swift = self._get_object_client()

        try:
            j2_role_file = swift.get_object(
                self.container, constants.OVERCLOUD_J2_ROLES_NAME)[1]
            role_data = yaml.safe_load(j2_role_file)
        except swiftexceptions.ClientException:
            LOG.info("No %s file found, skipping jinja templating"
                     % constants.OVERCLOUD_J2_ROLES_NAME)
            return

        j2_excl_data = self._get_j2_excludes_file()

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
        excl_templates = j2_excl_data.get('name')

        for f in [f.get('name') for f in container_files[1]]:
            # We do two templating passes here:
            # 1. *.role.j2.yaml - we template just the role name
            #    and create multiple files (one per role)
            # 2. *.j2.yaml - we template with all roles_data,
            #    and create one file common to all roles
            if f.endswith('.role.j2.yaml'):
                LOG.info("jinja2 rendering role template %s" % f)
                j2_template = swift.get_object(self.container, f)[1]
                LOG.info("jinja2 rendering roles %s" % ","
                         .join(role_names))
                for role in role_names:
                    j2_data = {'role': role}
                    LOG.info("jinja2 rendering role %s" % role)
                    out_f = "-".join(
                        [role.lower(),
                         os.path.basename(f).replace('.role.j2.yaml',
                                                     '.yaml')])
                    out_f_path = os.path.join(os.path.dirname(f), out_f)
                    if not (out_f_path in excl_templates):
                        self._j2_render_and_put(j2_template,
                                                j2_data,
                                                out_f_path)
                    else:
                        LOG.info("Skipping rendering of %s, defined in %s" %
                                 (out_f_path, j2_excl_data))

            elif f.endswith('.j2.yaml'):
                LOG.info("jinja2 rendering %s" % f)
                j2_template = swift.get_object(self.container, f)[1]
                j2_data = {'roles': role_data}
                out_f = f.replace('.j2.yaml', '.yaml')
                self._j2_render_and_put(j2_template, j2_data, out_f)

    def run(self):
        error_text = None
        ctx = context.ctx()
        swift = self._get_object_client()
        mistral = self._get_workflow_client()
        try:
            mistral_environment = mistral.environments.get(self.container)
        except Exception as mistral_err:
            error_text = six.text_type(mistral_err)
            LOG.exception(
                "Error retrieving Mistral Environment: %s" % self.container)
            return mistral_workflow_utils.Result(error=error_text)

        try:
            # if the jinja overcloud template exists, process it and write it
            # back to the swift container before continuing processing.  The
            # method called below should handle the case where the files are
            # not found in swift, but if they are found and an exception
            # occurs during processing, that exception will cause the
            # ProcessTemplatesAction to return an error result.
            self._process_custom_roles()
        except Exception as err:
            LOG.exception("Error occurred while processing custom roles.")
            return mistral_workflow_utils.Result(error=six.text_type(err))

        template_name = mistral_environment.variables.get('template')
        environments = mistral_environment.variables.get('environments')
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
            passwords = mistral_environment.variables.get('passwords', {})
            merged_params.update(passwords)
            # handle user set parameter values next in case a user has set
            # a new value for a password parameter
            params = mistral_environment.variables.get(
                'parameter_defaults', {})
            merged_params.update(params)
            if merged_params:
                env_temp_file = _create_temp_file(
                    {'parameter_defaults': merged_params})
                temp_files.append(env_temp_file)
                env_paths.append(env_temp_file)

            def _env_path_is_object(env_path):
                retval = env_path.startswith(swift.url)
                LOG.debug('_env_path_is_object %s: %s' % (env_path, retval))
                return retval

            def _object_request(method, url, token=ctx.auth_token):
                return requests.request(
                    method, url, headers={'X-Auth-Token': token}).content

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
            return mistral_workflow_utils.Result(error=error_text)

        files = dict(list(template_files.items()) + list(env_files.items()))

        return {
            'stack_name': self.container,
            'template': template,
            'environment': env,
            'files': files
        }
