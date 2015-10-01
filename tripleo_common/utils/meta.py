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
import yaml

from tripleo_common.core import constants
from tripleo_common.core import exception


def add_key_prefix(source):
    result = dict()
    for keyname, value in source.items():
        new_keyname = "%s%s" % (constants.OBJECT_META_KEY_PREFIX, keyname)
        result[new_keyname] = value
    return result


def remove_key_prefix(source):
    result = dict()
    for keyname, value in source.items():
        new_keyname = keyname.replace(constants.OBJECT_META_KEY_PREFIX, '')
        result[new_keyname] = value
    return result


def add_file_metadata(plan_files):
    cm = {k: v for (k, v) in plan_files.items()
          if v.get('meta', {}).get('file-type') == 'capabilities-map'}
    # if there is more than one capabilities-map file, throw an exception
    # if there is a capabilities-map file, then process it and set metadata
    # in files found
    if len(cm) > 1:
        raise exception.TooManyCapabilitiesMapFilesError()
    if len(cm) == 1:
        mapfile = yaml.load(list(cm.items())[0][1]['contents'])

        # identify the root template
        if mapfile['root_template']:
            if plan_files[mapfile['root_template']]:
                # if the file exists in the plan and has meta, update it
                # otherwise add meta dict
                if 'meta' in plan_files[mapfile['root_template']]:
                    plan_files[mapfile['root_template']]['meta'].update(
                        dict(constants.ROOT_TEMPLATE_META)
                    )
                else:
                    plan_files[mapfile['root_template']]['meta'] =\
                        dict(constants.ROOT_TEMPLATE_META)

        # identify all environments
        for topic in mapfile['topics']:
            for eg in topic['environment_groups']:
                for env in eg['environments']:
                    if 'meta' in plan_files[env['file']]:
                        plan_files[env['file']]['meta'].update(
                            dict(constants.ENVIRONMENT_META)
                        )
                    else:
                        plan_files[env['file']]['meta'] =\
                            dict(constants.ENVIRONMENT_META)

        # identify the root environment
        if mapfile['root_environment']:
            if plan_files[mapfile['root_environment']]:
                # if the file exists in the plan and has meta, update it
                # otherwise add meta dict
                if 'meta' in plan_files[mapfile['root_environment']]:
                    plan_files[mapfile['root_environment']]['meta'].update(
                        dict(constants.ROOT_ENVIRONMENT_META)
                    )
                else:
                    plan_files[mapfile['root_environment']]['meta'] =\
                        dict(constants.ROOT_ENVIRONMENT_META)
    return plan_files
