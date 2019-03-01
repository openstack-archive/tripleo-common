# Copyright 2017 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from heatclient.common import template_utils
import json
import os
import requests
import tempfile
import yaml

from tripleo_common import constants
from tripleo_common.utils import swift as swiftutils


def update_in_env(swift, env, key, value='', delete_key=False):
    """Update plan environment."""
    if delete_key:
        try:
            del env[key]
        except KeyError:
            pass
    else:
        try:
            env[key].update(value)
        except (KeyError, AttributeError):
            env[key] = value

    put_env(swift, env)
    return env


def get_env(swift, name):
    """Get plan environment from Swift and convert it to a dictionary."""
    env = yaml.safe_load(
        swiftutils.get_object_string(swift, name, constants.PLAN_ENVIRONMENT)
    )

    # Ensure the name is correct, as it will be used to update the
    # container later
    if env.get('name') != name:
        env['name'] = name

    return env


def put_env(swift, env):
    """Convert given environment to yaml and upload it to Swift."""
    swiftutils.put_object_string(
        swift,
        env['name'],
        constants.PLAN_ENVIRONMENT,
        yaml.safe_dump(env, default_flow_style=False)
    )


def get_user_env(swift, container_name):
    """Get user environment from Swift convert it to a dictionary."""
    return yaml.safe_load(
        swiftutils.get_object_string(swift, container_name,
                                     constants.USER_ENVIRONMENT))


def put_user_env(swift, container_name, env):
    """Convert given user environment to yaml and upload it to Swift."""
    swiftutils.put_object_string(
        swift,
        container_name,
        constants.USER_ENVIRONMENT,
        yaml.safe_dump(env, default_flow_style=False)
    )


def write_json_temp_file(data):
    """Writes the provided data to a json file and return the filename"""
    with tempfile.NamedTemporaryFile(delete=False, mode='wb') as temp_file:
        temp_file.write(json.dumps(data).encode('utf-8'))
    return temp_file.name


def object_request(method, url, token):
    """Fetch an object with the provided token"""
    response = requests.request(
        method, url, headers={'X-Auth-Token': token})
    response.raise_for_status()
    return response.content


def process_environments_and_files(swift, env_paths):
    """Wrap process_multiple_environments_and_files with swift object fetch"""
    def _env_path_is_object(env_path):
        return env_path.startswith(swift.url)

    # XXX this should belong in heatclient, but for the time being and backport
    # purposes, let's do that here for now.
    _cache = {}

    def _object_request(method, url, token=swift.token):
        if url not in _cache:
            _cache[url] = object_request(method, url, token)
        return _cache[url]

    return template_utils.process_multiple_environments_and_files(
        env_paths=env_paths,
        env_path_is_object=_env_path_is_object,
        object_request=_object_request)


def get_template_contents(swift, template_object):
    """Wrap get_template_contents with swift object fetch"""
    def _object_request(method, url, token=swift.token):
        return object_request(method, url, token)

    return template_utils.get_template_contents(
        template_object=template_object,
        object_request=_object_request)


def build_env_paths(swift, container, plan_env):
    environments = plan_env.get('environments', [])
    env_paths = []
    temp_env_paths = []

    for env in environments:
        if env.get('path'):
            env_paths.append(os.path.join(swift.url, container, env['path']))
        elif env.get('data'):
            env_file = write_json_temp_file(env['data'])
            temp_env_paths.append(env_file)

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
        env_temp_file = write_json_temp_file(
            {'parameter_defaults': merged_params})
        temp_env_paths.append(env_temp_file)

    registry = plan_env.get('resource_registry', {})
    if registry:
        env_temp_file = write_json_temp_file(
            {'resource_registry': registry})
        temp_env_paths.append(env_temp_file)

    env_paths.extend(temp_env_paths)
    return env_paths, temp_env_paths


def apply_environments_order(capabilities, environments):
    """traverses the capabilities and orders the environment files

    by dependency rules defined in capabilities-map, so that parent
    environments are first and children environments override these
    parents

    :param capabilities: dict representing capabilities-map.yaml file
    :param environments: list representing the environments section of the
                         plan-environments.yaml file
    :return: list containing ordered environments

    """
    # get ordering rules from capabilities-map file
    order_rules = {}
    for topic in capabilities.get('topics', []):
        for group in topic.get('environment_groups', []):
            for environment in group.get('environments', []):
                order_rules[environment['file']] = []
                if 'requires' in environment:
                    order_rules[environment['file']] \
                        = environment.get('requires', [])

    # apply ordering rules
    rest = []
    for e in environments:
        path = e.get('path', '')
        if path not in order_rules:
            environments.remove(e)
            rest.append(e)
            continue
        path_pos = environments.index(e)
        for requirement in order_rules[path]:
            if {'path': requirement} in environments:
                requirement_pos = environments.index({'path': requirement})
                if requirement_pos > path_pos:
                    item = environments.pop(requirement_pos)
                    environments.insert(path_pos, item)

    return environments + rest
