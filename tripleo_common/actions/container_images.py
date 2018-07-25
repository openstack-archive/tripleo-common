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
import os
import sys

from mistral_lib import actions
from swiftclient import exceptions as swiftexceptions
import yaml

from tripleo_common.actions import base
from tripleo_common.actions import heat_capabilities
from tripleo_common import constants
from tripleo_common.image import kolla_builder


LOG = logging.getLogger(__name__)


class PrepareContainerImageEnv(base.TripleOAction):
    """Populates env parameters with results from container image prepare

    :param container: Name of the Swift container / plan name
    """

    def __init__(self, container):
        super(PrepareContainerImageEnv, self).__init__()
        self.container = container

    def run(self, context):

        def ffunc(entry):
            return entry

        template_file = os.path.join(sys.prefix, 'share', 'tripleo-common',
                                     'container-images',
                                     'overcloud_containers.yaml.j2')

        builder = kolla_builder.KollaImageBuilder([template_file])
        result = builder.container_images_from_template(filter=ffunc)

        params = {}
        for entry in result:
            imagename = entry.get('imagename', '')
            if 'params' in entry:
                for p in entry.pop('params'):
                    params[p] = imagename
        swift = self.get_object_client(context)
        try:
            swift.put_object(
                self.container,
                constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                yaml.safe_dump(
                    {'parameter_defaults': params},
                    default_flow_style=False
                )
            )
        except swiftexceptions.ClientException as err:
            err_msg = ("Error updating %s for plan %s: %s" % (
                constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        environments = {constants.CONTAINER_DEFAULTS_ENVIRONMENT: True}

        update_action = heat_capabilities.UpdateCapabilitiesAction(
            environments, container=self.container)
        return update_action.run(context)
