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
import uuid


LOG = logging.getLogger(__name__)


def _process_params(flattened, params):
    for item in params:
        if item not in flattened['parameters']:
            param_obj = {}
            for key, value in params.get(item).items():
                camel_case_key = key[0].lower() + key[1:]
                param_obj[camel_case_key] = value
            param_obj['name'] = item
            flattened['parameters'][item] = param_obj
    return list(params)


def _flat_it(flattened, name, data):
    key = str(uuid.uuid4())
    value = {}
    value.update({
        'name': name,
        'id': key
    })
    if 'Type' in data:
        value['type'] = data['Type']
    if 'Description' in data:
        value['description'] = data['Description']
    if 'Parameters' in data:
        value['parameters'] = _process_params(flattened,
                                              data['Parameters'])
    if 'ParameterGroups' in data:
        value['parameter_groups'] = data['ParameterGroups']
    if 'NestedParameters' in data:
        nested = data['NestedParameters']
        nested_ids = []
        for nested_key in nested.keys():
            nested_data = _flat_it(flattened, nested_key,
                                   nested.get(nested_key))
            # nested_data will always have one key (and only one)
            nested_ids.append(list(nested_data)[0])

        value['resources'] = nested_ids

    flattened['resources'][key] = value
    return {key: value}


def preview_stack_and_network_configs(heat, processed_data,
                                      container, role_name):
    # stacks.preview method raises validation message if stack is
    # already deployed. here renaming container to get preview data.
    container_temp = container + "-TEMP"
    fields = {
        'template': processed_data['template'],
        'files': processed_data['files'],
        'environment': processed_data['environment'],
        'stack_name': container_temp,
    }
    preview_data = heat.stacks.preview(**fields)
    return get_network_config(preview_data, container_temp, role_name)


def get_network_config(preview_data, stack_name, role_name):
    result = None
    if preview_data:
        for res in preview_data.resources:
            net_script = process_preview_list(res, stack_name,
                                              role_name)
            if net_script:
                ns_len = len(net_script)
                start_index = (net_script.find(
                    "echo '{\"network_config\"", 0, ns_len) + 6)
                # In file network/scripts/run-os-net-config.sh
                end_str = "' > /etc/os-net-config/config.json"
                end_index = net_script.find(end_str, start_index, ns_len)
                if (end_index > start_index):
                    net_config = net_script[start_index:end_index]
                    if net_config:
                        result = json.loads(net_config)
                break
    if not result:
        err_msg = ("Unable to determine network config for role '%s'."
                   % role_name)
        LOG.exception(err_msg)
        raise RuntimeError(err_msg)
    return result


def process_preview_list(res, stack_name, role_name):
    if type(res) == list:
        for item in res:
            out = process_preview_list(item, stack_name, role_name)
            if out:
                return out
    elif type(res) == dict:
        res_stack_name = stack_name + '-' + role_name
        if res['resource_name'] == "OsNetConfigImpl" and \
            res['resource_identity'] and \
            res_stack_name in res['resource_identity']['stack_name']:
            return res['properties']['config']
    return None
