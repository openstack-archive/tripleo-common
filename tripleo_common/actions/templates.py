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
import tempfile as tf

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import tarball

LOG = logging.getLogger(__name__)


class UploadTemplatesAction(base.TripleOAction):
    """Upload default heat templates for TripleO.

    """
    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(UploadTemplatesAction, self).__init__()
        self.container = container

    def run(self):
        tht_base_path = constants.DEFAULT_TEMPLATES_PATH
        with tf.NamedTemporaryFile() as tmp_tarball:
            tarball.create_tarball(tht_base_path, tmp_tarball.name)
            tarball.tarball_extract_to_swift_container(
                self._get_object_client(),
                tmp_tarball.name,
                self.container)
