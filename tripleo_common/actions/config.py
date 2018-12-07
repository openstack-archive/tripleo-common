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

from swiftclient import exceptions as swiftexceptions

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
                 config_dir=None,
                 container_config=constants.CONFIG_CONTAINER_NAME,
                 config_type=None):
        super(GetOvercloudConfig, self).__init__(container)
        self.container = container
        self.config_dir = config_dir
        self.config_type = config_type

        if not self.config_dir:
            self.config_dir = tempfile.mkdtemp(prefix='tripleo-',
                                               suffix='-config')
        self.container_config = container_config

    def run(self, context):
        heat = self.get_orchestration_client(context)
        swift = self.get_object_client(context)

        # Since the config-download directory is now a git repo, first download
        # the existing config container if it exists so we can reuse the
        # existing git repo.
        try:
            swiftutils.download_container(swift, self.container_config,
                                          self.config_dir)
            # Delete the existing container before we re-upload, otherwise
            # files may not be fully overwritten.
            swiftutils.delete_container(swift, self.container_config)
        except swiftexceptions.ClientException as err:
            if err.http_status != 404:
                raise

        # Delete downloaded tarball as it will be recreated later and we don't
        # want to include the old tarball in the new tarball.
        old_tarball_path = os.path.join(
            self.config_dir, '%s.tar.gz' % self.container_config)
        if os.path.exists(old_tarball_path):
            os.unlink(old_tarball_path)

        config = ooo_config.Config(heat)
        message = ('Automatic commit by Mistral GetOvercloudConfig action.\n\n'
                   'User: {user}\n'
                   'Project: {project}'.format(user=context.user_name,
                                               project=context.project_name))
        config_path = config.download_config(self.container, self.config_dir,
                                             self.config_type,
                                             preserve_config_dir=True,
                                             commit_message=message)

        with tempfile.NamedTemporaryFile() as tmp_tarball:
            tarball.create_tarball(config_path, tmp_tarball.name,
                                   excludes=['.tox', '*.pyc', '*.pyo'])
            tarball.tarball_extract_to_swift_container(
                self.get_object_client(context),
                tmp_tarball.name,
                self.container_config)
            # Also upload the tarball to the container for use by export later
            with open(tmp_tarball.name, 'rb') as t:
                swift.put_object(self.container_config,
                                 '%s.tar.gz' % self.container_config, t)
        if os.path.exists(config_path):
            shutil.rmtree(config_path)


class DownloadConfigAction(templates.ProcessTemplatesAction):
    """Download the container config from swift

    This action downloads a container which contain the heat config output

    :param container: name of the Swift container / plan name
    """

    def __init__(self, container_config=constants.CONFIG_CONTAINER_NAME,
                 work_dir=None):
        super(DownloadConfigAction, self).__init__(container_config)
        self.container_config = container_config
        self.work_dir = work_dir
        if not self.work_dir:
            self.work_dir = tempfile.mkdtemp(
                prefix='tripleo-', suffix='-config')

    def run(self, context):
        swift = self.get_object_client(context)
        swiftutils.download_container(swift, self.container_config,
                                      self.work_dir)
        symlink_path = os.path.join(
            os.path.dirname(self.work_dir), 'config-download-latest')
        if os.path.exists(symlink_path):
            os.unlink(symlink_path)
        os.symlink(self.work_dir, symlink_path)
        return self.work_dir
