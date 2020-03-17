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

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import template as template_utils


class UploadTemplatesAction(base.TripleOAction):
    """Upload templates directory to Swift."""

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME,
                 dir_to_upload=constants.DEFAULT_TEMPLATES_PATH):
        super(UploadTemplatesAction, self).__init__()
        self.container = container
        self.dir_to_upload = dir_to_upload

    def run(self, context):
        swift = self.get_object_client(context)
        template_utils.upload_templates_as_tarball(
            swift, self.dir_to_upload, self.container)


class UploadPlanEnvironmentAction(base.TripleOAction):
    """Upload the plan environment into swift"""
    def __init__(self, plan_environment,
                 container=constants.DEFAULT_CONTAINER_NAME):
        super(UploadPlanEnvironmentAction, self).__init__()
        self.container = container
        self.plan_environment = plan_environment

    def run(self, context):
        # Get object client
        swift = self.get_object_client(context)
        # Push plan environment to the swift container
        plan_utils.put_env(swift, self.plan_environment)
