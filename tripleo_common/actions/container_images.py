# Copyright 2017 Red Hat, Inc.
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
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import plan as plan_utils


LOG = logging.getLogger(__name__)


class PrepareContainerImageEnv(base.TripleOAction):
    """Populates env parameters with results from container image prepare

    :param container: Name of the Swift container / plan name
    """

    def __init__(self, container):
        super(PrepareContainerImageEnv, self).__init__()
        self.container = container

    def run(self, context):
        swift = self.get_object_client(context)
        try:
            return plan_utils.update_plan_environment_with_image_parameters(
                swift, self.container, with_roledata=False)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error updating environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)


class PrepareContainerImageParameters(base.TripleOAction):
    """Populate environment with image params

    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(PrepareContainerImageParameters, self).__init__()
        self.container = container

    def run(self, context):
        self.context = context
        swift = self.get_object_client(context)

        try:
            return plan_utils.update_plan_environment_with_image_parameters(
                swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error updating environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)
