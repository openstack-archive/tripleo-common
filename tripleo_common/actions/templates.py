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
import json
import logging
import os
import requests
import tempfile as tf

from heatclient.common import template_utils
from mistral import context
from mistral.workflow import utils as mistral_workflow_utils

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
    """Upload default heat templates for TripleO.

    """
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

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(ProcessTemplatesAction, self).__init__()
        self.container = container

    def run(self):
        error_text = None
        ctx = context.ctx()
        swift = self._get_object_client()
        mistral = self._get_workflow_client()
        try:
            mistral_environment = mistral.environments.get(self.container)
        except Exception as mistral_err:
            error_text = mistral_err.message
            LOG.exception(
                "Error retrieving Mistral Environment: %s" % self.container)
            return mistral_workflow_utils.Result(error=error_text)

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

            # handle user set parameter values
            params = mistral_environment.variables.get('parameter_defaults')
            if params:
                env_temp_file = _create_temp_file(
                    {'parameter_defaults': params})
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
            error_text = str(err)
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
