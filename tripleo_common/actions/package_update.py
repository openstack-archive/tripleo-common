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

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import stack as stack_utils

LOG = logging.getLogger(__name__)


class UpdateStackAction(base.TripleOAction):

    def __init__(self, timeout, container=constants.DEFAULT_CONTAINER_NAME):
        super(UpdateStackAction, self).__init__()
        self.container = container
        self.timeout_mins = timeout

    def run(self, context):
        # get the stack. Error if doesn't exist
        heat = self.get_orchestration_client(context)
        swift = self.get_object_client(context)
        try:
            return stack_utils.stack_update(swift, heat,
                                            self.timeout_mins,
                                            self.container)
        except Exception as err:
            err_msg = ("Stack update failed for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)
