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
import json
import logging
import os

from mistral_lib import actions
import six

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import overcloudrc

LOG = logging.getLogger(__name__)


class OvercloudRcAction(base.TripleOAction):
    """Generate the overcloudrc for a plan

    Given the name of a container, generate the overcloudrc files needed to
    access the overcloud via the CLI.

    no_proxy is optional and is a comma-separated string of hosts that
    shouldn't be proxied
    """

    def __init__(self, container, no_proxy=""):
        super(OvercloudRcAction, self).__init__()
        self.container = container
        self.no_proxy = no_proxy

    def run(self, context):
        heat = self.get_orchestration_client(context)
        swift = self.get_object_client(context)
        try:
            return overcloudrc.create_overcloudrc(
                swift, heat, self.container, self.no_proxy)
        except Exception as err:
            LOG.exception(six.text_type(err))
            return actions.Result(six.text_type(err))


class DeploymentFailuresAction(base.TripleOAction):
    """Return all of the failures (if any) from deploying the plan

    :param plan: name of the Swift container / plan name
    """

    def __init__(self,
                 plan=constants.DEFAULT_CONTAINER_NAME,
                 work_dir=constants.MISTRAL_WORK_DIR,
                 ansible_errors_file=constants.ANSIBLE_ERRORS_FILE):
        super(DeploymentFailuresAction, self).__init__()
        self.plan = plan
        self.work_dir = work_dir
        self.ansible_errors_file = ansible_errors_file

    def _format_return(self, message, failures={}):
        return dict(message=message,
                    failures=failures)

    def run(self, context):
        try:
            failures_file = os.path.join(self.work_dir, self.plan,
                                         self.ansible_errors_file)
            failures = json.loads(open(failures_file).read())
            return self._format_return('', failures)
        except IOError:
            return self._format_return(
                'Ansible errors file not found at %s' % failures_file)
