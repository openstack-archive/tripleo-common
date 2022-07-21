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

import logging
import os
import sys

from heatclient import exc as heat_exc

from tripleo_common import constants
from tripleo_common.image import kolla_builder
from tripleo_common.utils import passwords as password_utils

LOG = logging.getLogger(__name__)


def default_image_params():

    def ffunc(entry):
        return entry

    template_file = os.path.join(sys.prefix, 'share', 'tripleo-common',
                                 'container-images',
                                 'tripleo_containers.yaml.j2')
    template_dir = os.path.join(sys.prefix, 'share', 'tripleo-common',
                                'container-images')
    builder = kolla_builder.KollaImageBuilder([template_file], template_dir)
    result = builder.container_images_from_template(filter=ffunc)

    params = {}
    for entry in result:
        imagename = entry.get('imagename', '')
        if 'params' in entry:
            for p in entry.pop('params'):
                params[p] = imagename
    return params


def generate_passwords(swift=None, heat=None,
                       container=constants.DEFAULT_CONTAINER_NAME,
                       rotate_passwords=False, rotate_pw_list=None,
                       passwords_env=None):
    """Generates passwords needed for Overcloud deployment

    This method generates passwords. By default, this method respects
    previously generated passwords and in stack environment.

    If rotate_passwords is set to True, then passwords will be replaced as
    follows:
    - if password names are specified in the rotate_pw_list, then only those
      passwords will be replaced.
    - otherwise, all passwords not in the DO_NOT_ROTATE list (as they require
      special handling, like KEKs and Fernet keys) will be replaced.
    """
    if rotate_pw_list is None:
        rotate_pw_list = []

    if passwords_env:
        stack_env = passwords_env
        placement_extracted = True
    elif heat is None:
        stack_env = None
        placement_extracted = True
    else:
        try:
            stack_env = heat.stacks.environment(
                stack_id=container)
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
        rotate_passwords=rotate_passwords,
        rotate_pw_list=rotate_pw_list)

    # NOTE(ansmith): if rabbit password previously generated and
    # stored, facilitate upgrade and use for oslo messaging in plan env
    if 'RabbitPassword' in passwords:
        for i in ('RpcPassword', 'NotifyPassword'):
            if i not in passwords:
                passwords[i] = passwords['RabbitPassword']

    # NOTE(owalsh): placement previously used NovaPassword
    # Default to the same password for PlacementPassword if it is an
    # upgrade (i.e NovaPassword is set) so we do not need to update the
    # password in keystone
    if not placement_extracted and 'NovaPassword' in passwords:
        LOG.debug('Setting PlacementPassword to NovaPassword')
        passwords['PlacementPassword'] = passwords['NovaPassword']

    return passwords


def rotate_fernet_keys(heat,
                       container=constants.DEFAULT_CONTAINER_NAME):
    try:
        stack_env = heat.stacks.environment(
            stack_id=container)
    except heat_exc.HTTPNotFound:
        raise RuntimeError('Can not rotate fernet keys without an'
                           'existing stack %s.' % container)

    parameter_defaults = stack_env.get('parameter_defaults', {})
    passwords = get_overriden_passwords({}, parameter_defaults)

    next_index = get_next_index(passwords['KeystoneFernetKeys'])
    keys_map = rotate_keys(passwords['KeystoneFernetKeys'],
                           next_index)
    max_keys = get_max_keys_value(parameter_defaults)
    return purge_excess_keys(max_keys, keys_map)


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
