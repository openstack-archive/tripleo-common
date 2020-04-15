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

from mistral_lib import actions
import six

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import config as ooo_config

LOG = logging.getLogger(__name__)


class GetOvercloudConfig(base.TripleOAction):
    """Get the Overcloud Config from the Heat outputs

    This action gets the Overcloud config from the Heat outputs and
    write it to the disk to be call with Ansible.

    :param container: name of the Swift container / plan name
     config_dir: directory where the config should be written
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME,
                 config_dir=None,
                 container_config=constants.CONFIG_CONTAINER_NAME,
                 config_type=None):
        super(GetOvercloudConfig, self).__init__()
        self.container = container
        self.config_dir = config_dir
        self.config_type = config_type
        self.container_config = container_config

    def run(self, context):
        heat = self.get_orchestration_client(context)
        swift = self.get_object_client(context)

        try:
            return ooo_config.get_overcloud_config(
                swift, heat, self.container, self.container_config,
                self.config_dir, self.config_type)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))


class DownloadConfigAction(base.TripleOAction):
    """Download the container config from swift

    This action downloads a container which contain the heat config output

    :param container: name of the Swift container / plan name
    """

    def __init__(self, container_config=constants.CONFIG_CONTAINER_NAME,
                 work_dir=None):
        super(DownloadConfigAction, self).__init__()
        self.container_config = container_config
        self.work_dir = work_dir

    def run(self, context):
        swift = self.get_object_client(context)
        try:
            return ooo_config.download_overcloud_config(
                swift, self.container_config, self.work_dir)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))
