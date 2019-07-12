# Copyright 2018, 2019 Red Hat, Inc.
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

import os
import yaml

from tripleo_common import constants


def _create_clouds_yaml(clouds_yaml):
    if not os.path.isfile(clouds_yaml):
        with open(clouds_yaml, "w") as f:
            yaml.safe_dump({"clouds": {}}, f, default_flow_style=False)
        os.chmod(clouds_yaml, 0o600)


def _create_clouds_yaml_dir(dir_path, user_id, group_id):
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)
        os.chown(dir_path, user_id, group_id)


def _read_clouds_yaml(clouds_yaml):
    with open(clouds_yaml, "r") as f:
        clouds = yaml.safe_load(f)
        if "clouds" not in clouds:
            clouds.update({"clouds": {}})

    return clouds


def _write_clouds_yaml(clouds_yaml, clouds):
    with open(clouds_yaml, "w") as f:
        yaml.safe_dump(clouds, f, default_flow_style=False)


def create_clouds_yaml(**kwargs):
    """Generates clouds.yaml file

    :param cloud: dict containing cloud data
    :param clouds_yaml_dir: Directory to create clouds.yaml file
    :param user_id: User id of the user owning the file
    :param group_id: Group id of the user owning the file
    """

    cloud = kwargs.get("cloud", None)
    dir_path = kwargs.get("cloud_yaml_dir", constants.GLOBAL_OS_DIR)
    clouds_yaml = os.path.join(dir_path, constants.CLOUDS_YAML_FILE)
    user_id = kwargs.get("user_id", 0)
    group_id = kwargs.get("group_id", 0)

    try:
        _create_clouds_yaml_dir(dir_path, user_id, group_id)
        _create_clouds_yaml(clouds_yaml)
        user_clouds = _read_clouds_yaml(clouds_yaml)
        user_clouds["clouds"].update(cloud)
        _write_clouds_yaml(clouds_yaml, user_clouds)
        os.chown(clouds_yaml, user_id, group_id)
        print("The clouds.yaml file is at {0}".format(clouds_yaml))

    except Exception as e:
        print("Create clouds.yaml failed: {}".format(e))
