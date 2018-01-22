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

from heatclient.common import template_utils

from tripleo_common import constants


def add_breakpoints_cleanup_into_env(env):
    template_utils.deep_update(env, {
        'resource_registry': {
            'resources': {'*': {'*': {
                constants.UPDATE_RESOURCE_NAME: {'hooks': []}}}}
        }
    })
