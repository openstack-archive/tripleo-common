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
import yaml

from mistral.workflow import utils as mistral_workflow_utils
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants

LOG = logging.getLogger(__name__)

default_container_headers = {
    constants.TRIPLEO_META_USAGE_KEY: 'plan'
}


class CreateContainerAction(base.TripleOAction):

    def __init__(self, container):
        super(CreateContainerAction, self).__init__()
        self.container = container

    def run(self):
        oc = self._get_object_client()
        # checks to see if a container with that name exists
        if self.container in [container["name"] for container in
                              oc.get_account()[1]]:
            result_string = ("A container with the name %s already"
                             " exists.") % self.container
            return mistral_workflow_utils.Result(
                None,
                result_string
            )
        oc.put_container(self.container, headers=default_container_headers)


class CreatePlanAction(base.TripleOAction):

    def __init__(self, container):
        super(CreatePlanAction, self).__init__()
        self.container = container

    def run(self):
        oc = self._get_object_client()
        env_data = {
            'name': self.container,
        }
        env_vars = {}
        error_text = None
        try:
            # parses capabilities to get root_template, root_environment
            mapfile = yaml.safe_load(
                oc.get_object(self.container, 'capabilities-map.yaml')[1])

            if mapfile['root_template']:
                env_vars['template'] = mapfile['root_template']
            if mapfile['root_environment']:
                env_vars['environments'] = [
                    {'path': mapfile['root_environment']}]

            env_data['variables'] = json.dumps(env_vars, sort_keys=True,)
            # creates environment
            self._get_workflow_client().environments.create(**env_data)
        except yaml.YAMLError as yaml_err:
            error_text = "Error parsing the yaml file: %s" % yaml_err
        except swiftexceptions.ClientException as obj_err:
            error_text = "File missing from container: %s" % obj_err
        except KeyError as key_err:
            error_text = ("capabilities-map.yaml missing key: "
                          "%s" % key_err)
        except Exception as err:
            error_text = "Error occurred creating plan: %s" % err

        if error_text:
            return mistral_workflow_utils.Result(error=error_text)
