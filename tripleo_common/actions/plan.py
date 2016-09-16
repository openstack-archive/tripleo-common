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

from heatclient import exc as heatexceptions
from mistral.workflow import utils as mistral_workflow_utils
from mistralclient.api import base as mistralclient_base
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common import exception

LOG = logging.getLogger(__name__)

default_container_headers = {
    constants.TRIPLEO_META_USAGE_KEY: 'plan'
}


class CreateContainerAction(base.TripleOAction):
    """Creates an object container

    This action creates an object container for a given name.  If a container
    with the same name already exists an exception is raised.
    """

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
    """Creates a plan

    Given a container, creates a Mistral environment with the same name,
    parses the capabilities map file and sets initial plan template and
    environment files.
    """

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

        # Check to see if an environment with that name already exists
        try:
            self._get_workflow_client().environments.get(self.container)
        except mistralclient_base.APIException:
            # The environment doesn't exist, as expected. Proceed.
            pass
        else:
            message = ("Unable to create plan. The Mistral environment "
                       "already exists")
            return mistral_workflow_utils.Result(None, message)

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


class UpdatePlanAction(base.TripleOAction):
    """Update a plan

    Given a container, update the Mistral environment with the same name,
    parses the capabilities map file and sets the initial plan template
    and environment files if they have changed since the plan was originally
    created.
    """

    def __init__(self, container):
        super(UpdatePlanAction, self).__init__()
        self.container = container

    def run(self):
        swift = self._get_object_client()
        mistral = self._get_workflow_client()

        error_text = None

        try:
            mapobject = swift.get_object(self.container,
                                         'capabilities-map.yaml')[1]
            mapfile = yaml.safe_load(mapobject)

            mistral_env = mistral.environments.get(self.container)

            # We always want the root template to match whatever is in the
            # capabilities map, so update that regardless.
            mistral_env.variables['root_template'] = mapfile['root_template']

            # Check to see if the root environment is already listed, if it
            # isn't - add it.
            # TODO(d0ugal): Users could get into a situation where they have
            #               an old root environment still added and they
            #               then have two after the new one is added.
            root_env = {'path': mapfile['root_environment']}
            if root_env not in mistral_env.variables['environments']:
                mistral_env.variables['environments'].insert(0, root_env)

            mistral.environments.update(
                name=self.container,
                variables=mistral_env.variables,
            )
        except yaml.YAMLError as yaml_err:
            error_text = "Error parsing the yaml file: %s" % yaml_err
        except swiftexceptions.ClientException as obj_err:
            error_text = "File missing from container: %s" % obj_err
        except KeyError as key_err:
            error_text = ("capabilities-map.yaml missing key: "
                          "%s" % key_err)
        if error_text:
            return mistral_workflow_utils.Result(error=error_text)


class ListPlansAction(base.TripleOAction):
    """Lists deployment plans

    This action lists all deployment plans residing in the undercloud.  A
    deployment plan consists of a container marked with metadata
    'x-container-meta-usage-tripleo' and a mistral environment with the same
    name as the container.
    """

    def __init__(self):
        super(ListPlansAction, self).__init__()

    def run(self):
        # plans consist of a container object and mistral environment
        # with the same name.  The container is marked with metadata
        # to ensure it isn't confused with another container
        plan_list = []
        oc = self._get_object_client()
        mc = self._get_workflow_client()
        for item in oc.get_account()[1]:
            container = oc.get_container(item['name'])[0]
            if constants.TRIPLEO_META_USAGE_KEY in container.keys():
                plan_list.append(item['name'])
        return list(set(plan_list).intersection(
            [env.name for env in mc.environments.list()]))


class DeletePlanAction(base.TripleOAction):
    """Deletes a plan and associated files

    Deletes a plan by deleting the container matching plan_name. It
    will not delete the plan if a stack exists with the same name.

    Raises StackInUseError if a stack with the same name as plan_name
    exists.
    """

    def __init__(self, container):
        super(DeletePlanAction, self).__init__()
        self.container = container

    def run(self):
        error_text = None
        # heat throws HTTPNotFound if the stack is not found
        try:
            stack = self._get_orchestration_client().stacks.get(self.container)
        except heatexceptions.HTTPNotFound:
            pass
        else:
            if stack is not None:
                raise exception.StackInUseError(name=self.container)

        try:
            swift = self._get_object_client()
            if self.container in [container["name"] for container in
                                  swift.get_account()[1]]:
                box = swift.get_container(self.container)
                # ensure container is a plan
                if box[0].get(constants.TRIPLEO_META_USAGE_KEY) == 'plan':
                    # FIXME(rbrady): remove delete_object loop when
                    # LP#1615830 is fixed.  See LP#1615825 for more info.
                    # delete files from plan
                    for data in box[1]:
                        swift.delete_object(self.container, data['name'])
                    # delete plan container
                    swift.delete_container(self.container)
                    # if mistral environment exists, delete it too
                    mistral = self._get_workflow_client()
                    if self.container in [env.name for env in
                                          mistral.environments.list()]:
                        # deletes environment
                        mistral.environments.delete(self.container)

        except swiftexceptions.ClientException as ce:
            LOG.exception("Swift error deleting plan.")
            error_text = ce.msg
        except Exception as err:
            LOG.exception("Error deleting plan.")
            error_text = err

        if error_text:
            return mistral_workflow_utils.Result(error=error_text)


class ListRolesAction(base.TripleOAction):
    """Returns a deployment plan's roles

    Parses overcloud.yaml and returns the Heat resources where
    type = OS::Heat::ResourceGroup

    :param container: name of the Swift container / plan name
    :return: list of roles in the container's deployment plan
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(ListRolesAction, self).__init__()
        self.container = container

    def run(self):
        try:
            mc = self._get_workflow_client()
            mistral_env = mc.environments.get(self.container)
            template_name = mistral_env.variables['template']

            oc = self._get_object_client()
            resources = yaml.safe_load(
                oc.get_object(self.container, template_name)[1])['resources']
        except Exception as mistral_err:
            err_msg = ("Error retrieving deployment plan: %s"
                       % mistral_err)
            LOG.exception(err_msg)
            return mistral_workflow_utils.Result(None, err_msg)

        roles = []
        for resource, details in resources.items():
            if details['type'] == constants.RESOURCE_GROUP_TYPE:
                roles.append(resource)
        return roles
