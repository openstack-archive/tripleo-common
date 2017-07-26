# Copyright 2016 Red Hat, Inc.
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
import logging
import os
import shutil
import tempfile

from tripleo_common.actions import templates
from tripleo_common import constants
from tripleo_common.utils import config as ooo_config
from tripleo_common.utils import swift as swiftutils
from tripleo_common.utils import tarball

LOG = logging.getLogger(__name__)


class GetOvercloudConfig(templates.ProcessTemplatesAction):
    """Get the Overcloud Config from the Heat outputs

    This action gets the Overcloud config from the Heat outputs and
    write it to the disk to be call with Ansible.

    :param container: name of the Swift container / plan name
     config_dir: directory where the config should be written
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME,
                 config_dir=tempfile.gettempdir(),
                 container_config=constants.CONFIG_CONTAINER_NAME):
        super(GetOvercloudConfig, self).__init__(container)
        self.container = container
        self.config_dir = config_dir
        self.container_config = container_config

    def run(self, context):
        heat = self.get_orchestration_client(context)
        config = ooo_config.Config(heat)
        config_path = config.download_config(self.container, self.config_dir)

        with tempfile.NamedTemporaryFile() as tmp_tarball:
            tarball.create_tarball(config_path, tmp_tarball.name)
            tarball.tarball_extract_to_swift_container(
                self.get_object_client(context),
                tmp_tarball.name,
                self.container_config)
        if os.path.exists(config_path):
            shutil.rmtree(config_path)


class DownloadConfigAction(templates.ProcessTemplatesAction):
    """Download the container config from swift

    This action downloads a container which contain the heat config output

    :param container: name of the Swift container / plan name
    """

    def __init__(self, container_config=constants.CONFIG_CONTAINER_NAME):
        super(DownloadConfigAction, self).__init__(container_config)
        self.container_config = container_config

    def run(self, context):
        swift = self.get_object_client(context)
        tmp_dir = tempfile.mkdtemp(prefix='tripleo-',
                                   suffix='-config')
        swiftutils.download_container(swift, self.container_config, tmp_dir)
        return tmp_dir
