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

import json
import logging
import os
import requests
import sys
import tempfile
import yaml
import zlib

from heatclient.common import template_utils
from heatclient import exc as heat_exc
import six
from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
from tripleo_common.image import kolla_builder
from tripleo_common.utils import passwords as password_utils
from tripleo_common.utils import swift as swiftutils
from tripleo_common.utils.validations import pattern_validator

LOG = logging.getLogger(__name__)


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


def format_cache_key(plan_name, key_name):
    return "__cache_{}_{}".format(plan_name, key_name)


def cache_get(swift, plan_name, key):
    """Retrieves the stored objects

    Returns None if there are any issues or no objects found

    """

    try:
        headers, body = swift.get_object(
            constants.TRIPLEO_CACHE_CONTAINER,
            format_cache_key(plan_name, key)
        )
        result = json.loads(zlib.decompress(body).decode())
        return result
    except swiftexceptions.ClientException:
        # cache does not exist, ignore
        pass
    except ValueError:
        # the stored json is invalid. Deleting
        cache_delete(swift, plan_name, key)
    return None


def cache_set(swift, plan_name, key, contents):
    """Stores an object

    Allows the storage of jsonable objects except for None
    Storing None equals to a cache delete.

    """

    if contents is None:
        cache_delete(swift, plan_name, key)
        return

    try:
        swift.head_container(constants.TRIPLEO_CACHE_CONTAINER)
    except swiftexceptions.ClientException:
        swift.put_container(constants.TRIPLEO_CACHE_CONTAINER)

    swift.put_object(
        constants.TRIPLEO_CACHE_CONTAINER,
        format_cache_key(plan_name, key),
        zlib.compress(json.dumps(contents).encode()))


def cache_delete(swift, plan_name, key):
    try:
        swift.delete_object(
            constants.TRIPLEO_CACHE_CONTAINER,
            format_cache_key(plan_name, key))
    except swiftexceptions.ClientException:
        # cache or container does not exist. Ignore
        pass


def create_plan_container(swift, plan_name):
    if not pattern_validator(constants.PLAN_NAME_PATTERN, plan_name):
        message = ("The plan name must "
                   "only contain letters, numbers or dashes")
        raise RuntimeError(message)

    # checks to see if a container with that name exists
    if plan_name in [container["name"] for container in
                     swift.get_account()[1]]:
        message = ("A container with the name %s already "
                   "exists.") % plan_name
        raise RuntimeError(message)
    default_container_headers = {constants.TRIPLEO_META_USAGE_KEY: 'plan'}
    swift.put_container(plan_name, headers=default_container_headers)


def update_plan_environment(swift, environments,
                            container=constants.DEFAULT_CONTAINER_NAME):
    env = get_env(swift, container)
    for k, v in environments.items():
        found = False
        if {'path': k} in env['environments']:
            found = True
        if v:
            if not found:
                env['environments'].append({'path': k})
        else:
            if found:
                env['environments'].remove({'path': k})

    cache_delete(swift, container, "tripleo.parameters.get")
    put_env(swift, env)
    return env


def get_role_data(swift, container=constants.DEFAULT_CONTAINER_NAME):
    try:
        j2_role_file = swiftutils.get_object_string(
            swift,
            container,
            constants.OVERCLOUD_J2_ROLES_NAME)
        role_data = yaml.safe_load(j2_role_file)
    except swiftexceptions.ClientException:
        LOG.info("No %s file found, not filtering container images by role"
                 % constants.OVERCLOUD_J2_ROLES_NAME)
        role_data = None
    return role_data


def default_image_params():

    def ffunc(entry):
        return entry

    template_file = os.path.join(sys.prefix, 'share', 'tripleo-common',
                                 'container-images',
                                 'tripleo_containers.yaml.j2')
    builder = kolla_builder.KollaImageBuilder([template_file])
    result = builder.container_images_from_template(filter=ffunc)

    params = {}
    for entry in result:
        imagename = entry.get('imagename', '')
        if 'params' in entry:
            for p in entry.pop('params'):
                params[p] = imagename
    return params


def update_plan_environment_with_image_parameters(
    swift, container=constants.DEFAULT_CONTAINER_NAME,
    with_roledata=True):
    try:
        # ensure every image parameter has a default value, even if prepare
        # didn't return it
        params = default_image_params()

        if with_roledata:
            plan_env = get_env(swift, container)
            env_paths, temp_env_paths = build_env_paths(
                swift, container, plan_env)
            env_files, env = process_environments_and_files(
                swift, env_paths)

            role_data = get_role_data(swift)
            image_params = kolla_builder.container_images_prepare_multi(
                env, role_data, dry_run=True)
            if image_params:
                params.update(image_params)

    except Exception as err:
        LOG.exception("Error occurred while updating plan files.")
        raise RuntimeError(six.text_type(err))
    finally:
        # cleanup any local temp files
        if with_roledata:
            for f in temp_env_paths:
                os.remove(f)

    try:
        swiftutils.put_object_string(
            swift,
            container,
            constants.CONTAINER_DEFAULTS_ENVIRONMENT,
            yaml.safe_dump(
                {'parameter_defaults': params},
                default_flow_style=False
            )
        )
    except swiftexceptions.ClientException as err:
        err_msg = ("Error updating %s for plan %s: %s" % (
            constants.CONTAINER_DEFAULTS_ENVIRONMENT, container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    environments = {constants.CONTAINER_DEFAULTS_ENVIRONMENT: True}

    try:
        env = update_plan_environment(swift, environments,
                                      container=container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error updating environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)
    return env


def generate_passwords(swift, heat, mistral=None,
                       container=constants.DEFAULT_CONTAINER_NAME,
                       rotate_passwords=False, rotate_pw_list=None):
    """Generates passwords needed for Overcloud deployment

    This method generates passwords and ensures they are stored in the
    plan environment. By default, this method respects previously
    generated passwords and adds new passwords as necessary.

    If rotate_passwords is set to True, then passwords will be replaced as
    follows:
    - if password names are specified in the rotate_pw_list, then only those
      passwords will be replaced.
    - otherwise, all passwords not in the DO_NOT_ROTATE list (as they require
      special handling, like KEKs and Fernet keys) will be replaced.
    """
    if rotate_pw_list is None:
        rotate_pw_list = []
    try:
        env = get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        return RuntimeError(err_msg)

    try:
        stack_env = heat.stacks.environment(
            stack_id=container)

        # legacy heat resource names from overcloud.yaml
        # We don't modify these to avoid changing defaults
        for pw_res in constants.LEGACY_HEAT_PASSWORD_RESOURCE_NAMES:
            try:
                param_defaults = stack_env.get('parameter_defaults', {})
                if pw_res not in param_defaults:
                    res = heat.resources.get(container, pw_res)
                    param_defaults[pw_res] = res.attributes['value']
            except heat_exc.HTTPNotFound:
                LOG.debug('Heat resouce not found: %s' % pw_res)
                pass

    except heat_exc.HTTPNotFound:
        stack_env = None

    placement_extracted = False
    try:
        # We can't rely on the existence of PlacementPassword to
        # determine if placement extraction has occured as it was added
        # in stein while the service extraction was delayed to train.
        # Inspect the endpoint map instead.
        endpoint_res = heat.resources.get(container, 'EndpointMap')
        endpoints = endpoint_res.attributes.get('endpoint_map', None)
        placement_extracted = endpoints and 'PlacementPublic' in endpoints
    except heat_exc.HTTPNotFound:
        pass

    passwords = password_utils.generate_passwords(
        stack_env=stack_env,
        rotate_passwords=rotate_passwords
    )

    # if passwords don't yet exist in plan environment
    if 'passwords' not in env:
        env['passwords'] = {}

    # NOTE(ansmith): if rabbit password previously generated and
    # stored, facilitate upgrade and use for oslo messaging in plan env
    if 'RabbitPassword' in env['passwords']:
        for i in ('RpcPassword', 'NotifyPassword'):
            if i not in env['passwords']:
                env['passwords'][i] = env['passwords']['RabbitPassword']

    # NOTE(owalsh): placement previously used NovaPassword
    # Default to the same password for PlacementPassword if it is an
    # upgrade (i.e NovaPassword is set) so we do not need to update the
    # password in keystone
    if not placement_extracted and 'NovaPassword' in env['passwords']:
        LOG.debug('Setting PlacementPassword to NovaPassword')
        env['passwords']['PlacementPassword'] = \
            env['passwords']['NovaPassword']

    # ensure all generated passwords are present in plan env,
    # but respect any values previously generated and stored
    for name, password in passwords.items():
        if name not in env['passwords']:
            env['passwords'][name] = password

    if rotate_passwords:
        if len(rotate_pw_list) > 0:
            for name in rotate_pw_list:
                env['passwords'][name] = passwords[name]
        else:
            for name, password in passwords.items():
                if name not in constants.DO_NOT_ROTATE_LIST:
                    env['passwords'][name] = password

    try:
        put_env(swift, env)
    except swiftexceptions.ClientException as err:
        err_msg = "Error uploading to container: %s" % err
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    cache_delete(swift, container, "tripleo.parameters.get")
    return env['passwords']


def update_plan_rotate_fernet_keys(swift,
                                   container=constants.DEFAULT_CONTAINER_NAME):
    try:
        env = get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    parameter_defaults = env.get('parameter_defaults', {})
    passwords = get_overriden_passwords(env.get(
        'passwords', {}), parameter_defaults)

    next_index = get_next_index(passwords['KeystoneFernetKeys'])
    keys_map = rotate_keys(passwords['KeystoneFernetKeys'],
                           next_index)
    max_keys = get_max_keys_value(parameter_defaults)
    keys_map = purge_excess_keys(max_keys, keys_map)

    env['passwords']['KeystoneFernetKeys'] = keys_map

    try:
        put_env(swift, env)
    except swiftexceptions.ClientException as err:
        err_msg = "Error uploading to container: %s" % err
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)

    cache_delete(swift, container, "tripleo.parameters.get")
    return keys_map


def get_overriden_passwords(env_passwords, parameter_defaults):
    for name in constants.PASSWORD_PARAMETER_NAMES:
        if name in parameter_defaults:
            env_passwords[name] = parameter_defaults[name]
    return env_passwords


def get_key_index_from_path(path):
    return int(path[path.rfind('/') + 1:])


def get_next_index(keys_map):
    return get_key_index_from_path(
        max(keys_map, key=get_key_index_from_path)) + 1


def get_key_path(index):
    return password_utils.KEYSTONE_FERNET_REPO + str(index)


def rotate_keys(keys_map, next_index):
    next_index_path = get_key_path(next_index)
    zero_index_path = get_key_path(0)

    # promote staged key to be new primary
    keys_map[next_index_path] = keys_map[zero_index_path]
    # Set new staged key
    keys_map[zero_index_path] = {
        'content': password_utils.create_keystone_credential()}
    return keys_map


def get_max_keys_value(parameter_defaults):
    # The number of max keys should always be positive. The minimum amount
    # of keys is 3.
    return max(parameter_defaults.get('KeystoneFernetMaxActiveKeys', 5), 3)


def purge_excess_keys(max_keys, keys_map):
    current_repo_size = len(keys_map)
    if current_repo_size <= max_keys:
        return keys_map
    key_paths = sorted(keys_map.keys(), key=get_key_index_from_path)

    keys_to_be_purged = current_repo_size - max_keys

    for key_path in key_paths[1:keys_to_be_purged + 1]:
        del keys_map[key_path]
    return keys_map
