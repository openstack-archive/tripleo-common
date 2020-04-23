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
