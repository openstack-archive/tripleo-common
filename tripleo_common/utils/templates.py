# Copyright 2015 Red Hat, Inc.
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
import tempfile
import yaml

from heatclient.common import template_utils

LOG = logging.getLogger(__name__)


def _get_dict_from_env_string(env_name, env_string):
    """Returns environment dict, either from yaml or json."""
    if '.yaml' in env_name:
        return yaml.load(env_string)
    else:
        return json.loads(env_string)


def deep_update(base, new):
    """Updates a given dictionary with a nested dictionary of varying depth

    :param base: The dictionary to update
    :param new: The dictionary to merge into the base dictionary
    :return: a combined nested dictionary
    """
    for key, val in new.items():
        if isinstance(val, dict):
            tmp = deep_update(base.get(key, {}), val)
            base[key] = tmp
        else:
            base[key] = val
    return base


def preprocess_templates(swift_base_url, container_name, template,
                         environments, auth_token):
    """Pre-processes and organizes plan files

    This method processes heat templates and environments by collecting the
    remote paths of the files in a given swift container and combining them
    with given environment data and uses methods in python-heatclient to get
    template contents and process the files with respect to order.  This
    method also sets the stack_name returned in the results to the same name
    as the given container.

    :param swift_base_url: the endpoint url for swift
    :param container_name: name of the swift container that holds heat
                           templates for a deployment plan
    :param template: the root template of a given plan
    :param environments: environment files or yaml contents to be combined
    :param auth_token: keystone authentication token for accessing heat and
                       swift to retrieve file contents.
    :return: dict of heat stack name, template, combined environment and files
    """
    template_object = os.path.join(swift_base_url, container_name, template)
    env_paths = []
    temp_files = []
    LOG.debug('Template: %s' % template)
    LOG.debug('Environments: %s' % environments)
    try:
        for env in environments:
            if env.get('path'):
                env_paths.append(os.path.join(swift_base_url, container_name,
                                              env['path']))
            elif env.get('data'):
                handle, env_temp_file = tempfile.mkstemp()
                with open(env_temp_file, 'w') as temp_file:
                    temp_file.write(json.dumps(env['data']))
                    os.close(handle)
                temp_files.append(env_temp_file)
                env_paths.append(env_temp_file)

        def _env_path_is_object(env_path):
            if env_path in temp_files:
                LOG.debug('_env_path_is_object %s: False' % env_path)
                return False
            else:
                LOG.debug('_env_path_is_object %s: True' % env_path)
                return True

        def _object_request(method, url, token=auth_token):
            return requests.request(method, url,
                                    headers={'X-Auth-Token': token}).content

        template_files, template = template_utils.get_template_contents(
            template_object=template_object,
            object_request=_object_request)

        env_files, env = (
            template_utils.process_multiple_environments_and_files(
                env_paths=env_paths,
                env_path_is_object=_env_path_is_object,
                object_request=_object_request))
    finally:
        # cleanup any local temp files
        for f in temp_files:
            os.remove(f)

    files = dict(list(template_files.items()) + list(env_files.items()))

    return {
        'stack_name': container_name,
        'template': template,
        'environment': env,
        'files': files
    }
