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
import yaml

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


def process_plan_data(plan_data):
    """Preprocesses and organizes plan files for heatclient interaction

    This method separates the root template, environments and other
    associated files in preparation to send to heatclient for validation
    or deployment.  The environment files are merged with the temporary
    environment information stored in the deployment parameters.

    :param plan_data: the files stored in a plan
    :return: template, merged environment and associated files
    """
    template = ''
    environment = {}
    env_items = []
    temp_env_items = []
    files = {}

    for key, val in plan_data.items():
        file_type = val.get('meta', {}).get('file-type')
        enabled = val.get('meta', {}).get('enabled')
        if not file_type:
            files[key] = val['contents']
        elif file_type == 'environment' and enabled:
            env_items.append({'name': key,
                              'meta': val['meta'],
                              'contents': val['contents']})
        elif file_type == 'temp-environment':
            temp_env_items.append({'name': key,
                                   'meta': val['meta'],
                                   'contents': val['contents']})
        elif file_type == 'root-template':
            template = val['contents']
        elif file_type == 'root-environment' and enabled:
            environment = _get_dict_from_env_string(key, val['contents'])

    # merge environment files
    for item in env_items:
        env_dict = _get_dict_from_env_string(item['name'], item['contents'])
        environment = deep_update(environment, env_dict)

    # merge the temporary environment files last
    for item in temp_env_items:
        env_dict = _get_dict_from_env_string(item['name'], item['contents'])
        environment = deep_update(environment, env_dict)

    return template, environment, files


def find_root_template(plan_files):
    return {k: v for (k, v) in plan_files.items()
            if v.get('meta', {}).get('file-type') == 'root-template'}
