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
import yaml

from tripleo_common import constants


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
        swift.get_object(name, constants.PLAN_ENVIRONMENT)[1]
    )

    # Ensure the name is correct, as it will be used to update the
    # container later
    if env.get('name') != name:
        env['name'] = name

    return env


def put_env(swift, env):
    """Convert given environment to yaml and upload it to Swift."""
    swift.put_object(
        env['name'],
        constants.PLAN_ENVIRONMENT,
        yaml.safe_dump(env, default_flow_style=False)
    )
