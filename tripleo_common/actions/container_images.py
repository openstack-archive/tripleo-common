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

import copy
import logging
import os
import sys

from mistral_lib import actions
import six
from swiftclient import exceptions as swiftexceptions
import yaml

from tripleo_common.actions import base
from tripleo_common.actions import heat_capabilities
from tripleo_common import constants
from tripleo_common.image import kolla_builder
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import swift as swiftutils


LOG = logging.getLogger(__name__)


def default_image_params():
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
    return params


class PrepareContainerImageEnv(base.TripleOAction):
    """Populates env parameters with results from container image prepare

    :param container: Name of the Swift container / plan name
    """

    def __init__(self, container):
        super(PrepareContainerImageEnv, self).__init__()
        self.container = container

    def run(self, context):

        params = default_image_params()
        swift = self.get_object_client(context)
        try:
            swiftutils.put_object_string(
                swift,
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


class PrepareContainerImageParameters(base.TripleOAction):
    """Populate environment with image params

    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(PrepareContainerImageParameters, self).__init__()
        self.container = container

    def _get_role_data(self, swift):
        try:
            j2_role_file = swiftutils.get_object_string(
                swift,
                self.container,
                constants.OVERCLOUD_J2_ROLES_NAME)
            role_data = yaml.safe_load(j2_role_file)
        except swiftexceptions.ClientException:
            LOG.info("No %s file found, not filtering container images by role"
                     % constants.OVERCLOUD_J2_ROLES_NAME)
            role_data = None
        return role_data

    def run(self, context):
        self.context = context
        swift = self.get_object_client(context)

        try:
            plan_env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        try:
            env_paths, temp_env_paths = plan_utils.build_env_paths(
                swift, self.container, plan_env)
            env_files, env = plan_utils.process_environments_and_files(
                swift, env_paths)

            # ensure every image parameter has a default value, even if prepare
            # didn't return it
            params = default_image_params()

            role_data = self._get_role_data(swift)
            image_params = kolla_builder.container_images_prepare_multi(
                env, role_data, dry_run=True)
            if image_params:
                params.update(image_params)

        except Exception as err:
            LOG.exception("Error occurred while processing plan files.")
            return actions.Result(error=six.text_type(err))
        finally:
            # cleanup any local temp files
            for f in temp_env_paths:
                os.remove(f)

        try:
            swiftutils.put_object_string(
                swift,
                self.container,
                constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                yaml.safe_dump(
                    {'parameter_defaults': params},
                    default_flow_style=False
                )
            )
        except swiftexceptions.ClientException as err:
            err_msg = ("Error updating %s for plan %s: %s" % (
                constants.CONTAINER_DEFAULTS_ENVIRONMENT, self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        environments = {constants.CONTAINER_DEFAULTS_ENVIRONMENT: True}

        update_action = heat_capabilities.UpdateCapabilitiesAction(
            environments, container=self.container)
        return update_action.run(context)


class ContainerImagePrepareDefault(base.TripleOAction):
    """ContainerImagePrepare default parameters

    """

    def __init__(self, values):

        super(ContainerImagePrepareDefault, self).__init__()
        self.values = values

    def run(self, context):
        cip = copy.deepcopy(kolla_builder.CONTAINER_IMAGE_PREPARE_PARAM)

        for entry in cip:
            if 'push_destination' in self.values:
                entry['push_destination'] = self.values['push_destination']

            if 'tag_from_label' in self.values:
                entry['tag_from_label'] = self.values['tag_from_label']

            if 'namespace' in self.values:
                entry['set']['namespace'] = self.values['namespace']

            if 'name_prefix' in self.values:
                entry['set']['name_prefix'] = self.values['name_prefix']

            if 'name_suffix' in self.values:
                entry['set']['name_suffix'] = self.values['name_suffix']

            if 'tag' in self.values:
                entry['set']['tag'] = self.values['tag']

        return {
            'ContainerImagePrepare': cip
        }
