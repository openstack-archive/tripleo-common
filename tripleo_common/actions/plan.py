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
import shutil
import tempfile
import yaml

from heatclient import exc as heatexceptions
from mistral.workflow import utils as mistral_workflow_utils
from mistralclient.api import base as mistralclient_base
from oslo_concurrency import processutils
import six
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common import exception
from tripleo_common.utils import swift as swiftutils
from tripleo_common.utils import tarball
from tripleo_common.utils.validations import pattern_validator


LOG = logging.getLogger(__name__)

default_container_headers = {
    constants.TRIPLEO_META_USAGE_KEY: 'plan'
}


class PlanEnvMixin(object):
    @staticmethod
    def get_plan_env_dict(swift, container):
        """Retrieves the plan environment from Swift.

        Loads a plan environment file with a given container name from Swift.
        Makes sure that the file contains valid YAML and that the mandatory
        fields are present in the environment.

        If the plan environment file is missing from Swift, fall back to the
        capabilities-map.yaml.

        Returns the plan environment dictionary, and a boolean indicator
        whether the plan environment file was missing from Swift.
        """
        plan_env_missing = False

        try:
            plan_env = swift.get_object(container,
                                        constants.PLAN_ENVIRONMENT)[1]
        except swiftexceptions.ClientException:
            # If the plan environment file is missing from Swift, look for
            # capabilities-map.yaml instead
            plan_env_missing = True
            try:
                plan_env = swift.get_object(container,
                                            'capabilities-map.yaml')[1]
            except swiftexceptions.ClientException as err:
                raise exception.PlanOperationError(
                    "File missing from container: %s" % err)

        try:
            plan_env_dict = yaml.safe_load(plan_env)
        except yaml.YAMLError as err:
            raise exception.PlanOperationError(
                "Error parsing the yaml file: %s" % err)

        if plan_env_missing:
            plan_env_dict = {
                'environments': [{'path': plan_env_dict['root_environment']}],
                'template': plan_env_dict['root_template'],
                'version': 1.0
            }

        for key in ('environments', 'template', 'version'):
            if key not in plan_env_dict:
                raise exception.PlanOperationError(
                    "%s missing key: %s" % (constants.PLAN_ENVIRONMENT, key))

        return plan_env_dict, plan_env_missing


class CreateContainerAction(base.TripleOAction):
    """Creates an object container

    This action creates an object container for a given name.  If a container
    with the same name already exists an exception is raised.
    """

    def __init__(self, container):
        super(CreateContainerAction, self).__init__()
        self.container = container

    def run(self):
        oc = self.get_object_client()

        # checks to see if a container has a valid name
        if not pattern_validator(constants.PLAN_NAME_PATTERN, self.container):
            message = ("Unable to create plan. The plan name must "
                       "only contain letters, numbers or dashes")
            return mistral_workflow_utils.Result(error=message)

        # checks to see if a container with that name exists
        if self.container in [container["name"] for container in
                              oc.get_account()[1]]:
            result_string = ("A container with the name %s already"
                             " exists.") % self.container
            return mistral_workflow_utils.Result(error=result_string)
        oc.put_container(self.container, headers=default_container_headers)


class CreatePlanAction(base.TripleOAction, PlanEnvMixin):
    """Creates a plan

    Given a container, creates a Mistral environment with the same name.
    The contents of the environment are imported from the plan environment
    file, which must contain entries for `template`, `environments` and
    `version` at a minimum.
    """

    def __init__(self, container):
        super(CreatePlanAction, self).__init__()
        self.container = container

    def run(self):
        swift = self.get_object_client()
        mistral = self.get_workflow_client()
        env_data = {
            'name': self.container,
        }

        if not pattern_validator(constants.PLAN_NAME_PATTERN, self.container):
            message = ("Unable to create plan. The plan name must "
                       "only contain letters, numbers or dashes")
            return mistral_workflow_utils.Result(error=message)

        # Check to see if an environment with that name already exists
        try:
            mistral.environments.get(self.container)
        except mistralclient_base.APIException:
            # The environment doesn't exist, as expected. Proceed.
            pass
        else:
            message = ("Unable to create plan. The Mistral environment "
                       "already exists")
            return mistral_workflow_utils.Result(error=message)

        # Get plan environment from Swift
        try:
            plan_env_dict, plan_env_missing = self.get_plan_env_dict(
                swift, self.container)
        except exception.PlanOperationError as err:
            return mistral_workflow_utils.Result(error=six.text_type(err))

        # Create mistral environment
        env_data['variables'] = json.dumps(plan_env_dict, sort_keys=True)
        try:
            mistral.environments.create(**env_data)
        except Exception as err:
            message = "Error occurred creating plan: %s" % err
            return mistral_workflow_utils.Result(error=message)

        # Delete the plan environment file from Swift, as it is no long needed.
        # (If we were to leave the environment file behind, we would have to
        # take care to keep it in sync with the actual contents of the Mistral
        # environment. To avoid that, we simply delete it.)
        # TODO(akrivoka): Once the 'Deployment plan management changes' spec
        # (https://review.openstack.org/#/c/438918/) is implemented, we will no
        # longer use Mistral environments for holding the plan data, so this
        # code can go away.
        if not plan_env_missing:
            try:
                swift.delete_object(self.container, constants.PLAN_ENVIRONMENT)
            except swiftexceptions.ClientException as err:
                message = "Error deleting file from container: %s" % err
                return mistral_workflow_utils.Result(error=message)


class UpdatePlanAction(base.TripleOAction, PlanEnvMixin):
    """Updates a plan

    Given a container, update the Mistral environment with the same name.
    The contents of the environment are imported (overwritten) from the plan
    environment file, which must contain entries for `template`, `environments`
     and `version` at a minimum.
    """

    def __init__(self, container):
        super(UpdatePlanAction, self).__init__()
        self.container = container

    def run(self):
        swift = self.get_object_client()
        mistral = self.get_workflow_client()

        # Get plan environment from Swift
        try:
            plan_env_dict, plan_env_missing = self.get_plan_env_dict(
                swift, self.container)
        except exception.PlanOperationError as err:
            return mistral_workflow_utils.Result(error=six.text_type(err))

        # Update mistral environment with contents from plan environment file
        variables = json.dumps(plan_env_dict, sort_keys=True)
        try:
            mistral.environments.update(
                name=self.container, variables=variables)
        except mistralclient_base.APIException:
            message = "Error updating mistral environment: %s" % self.container
            return mistral_workflow_utils.Result(error=message)

        # Delete the plan environment file from Swift, as it is no long needed.
        # (If we were to leave the environment file behind, we would have to
        # take care to keep it in sync with the actual contents of the Mistral
        # environment. To avoid that, we simply delete it.)
        # TODO(akrivoka): Once the 'Deployment plan management changes' spec
        # (https://review.openstack.org/#/c/438918/) is implemented, we will no
        # longer use Mistral environments for holding the plan data, so this
        # code can go away.
        if not plan_env_missing:
            try:
                swift.delete_object(self.container, constants.PLAN_ENVIRONMENT)
            except swiftexceptions.ClientException as err:
                message = "Error deleting file from container: %s" % err
                return mistral_workflow_utils.Result(error=message)


class ListPlansAction(base.TripleOAction):
    """Lists deployment plans

    This action lists all deployment plans residing in the undercloud.  A
    deployment plan consists of a container marked with metadata
    'x-container-meta-usage-tripleo' and a mistral environment with the same
    name as the container.
    """

    def run(self):
        # plans consist of a container object and mistral environment
        # with the same name.  The container is marked with metadata
        # to ensure it isn't confused with another container
        plan_list = []
        oc = self.get_object_client()
        mc = self.get_workflow_client()
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
            stack = self.get_orchestration_client().stacks.get(self.container)
        except heatexceptions.HTTPNotFound:
            pass
        else:
            if stack is not None:
                raise exception.StackInUseError(name=self.container)

        try:
            swift = self.get_object_client()
            swiftutils.delete_container(swift, self.container)

            # if mistral environment exists, delete it too
            mistral = self.get_workflow_client()
            if self.container in [env.name for env in
                                  mistral.environments.list()]:
                # deletes environment
                mistral.environments.delete(self.container)
        except swiftexceptions.ClientException as ce:
            LOG.exception("Swift error deleting plan.")
            error_text = ce.msg
        except Exception as err:
            LOG.exception("Error deleting plan.")
            error_text = six.text_type(err)

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
            mc = self.get_workflow_client()
            mistral_env = mc.environments.get(self.container)
            template_name = mistral_env.variables['template']

            oc = self.get_object_client()
            resources = yaml.safe_load(
                oc.get_object(self.container, template_name)[1])['resources']
        except Exception as mistral_err:
            err_msg = ("Error retrieving deployment plan: %s"
                       % mistral_err)
            LOG.exception(err_msg)
            return mistral_workflow_utils.Result(error=err_msg)

        roles = []
        for resource, details in resources.items():
            if details['type'] == constants.RESOURCE_GROUP_TYPE:
                roles.append(resource)
        return roles


class ExportPlanAction(base.TripleOAction):
    """Exports a deployment plan

    This action exports a deployment plan with a given name. First, the plan
    templates are downloaded from the Swift container. Then the plan
    environment file is generated from the associated Mistral environment.
    Finally, both the templates and the plan environment file are packaged up
    in a tarball and uploaded to Swift.
    """

    def __init__(self, plan, delete_after, exports_container):
        super(ExportPlanAction, self).__init__()
        self.plan = plan
        self.delete_after = delete_after
        self.exports_container = exports_container

    def _download_templates(self, swift, tmp_dir):
        """Download templates to a temp folder."""
        template_files = swift.get_container(self.plan)[1]

        for tf in template_files:
            filename = tf['name']
            contents = swift.get_object(self.plan, filename)[1]
            path = os.path.join(tmp_dir, filename)
            dirname = os.path.dirname(path)

            if not os.path.exists(dirname):
                os.makedirs(dirname)

            with open(path, 'w') as f:
                f.write(contents)

    def _generate_plan_env_file(self, mistral, tmp_dir):
        """Generate plan environment file and add it to specified folder."""
        environment = mistral.environments.get(self.plan).variables
        yaml_string = yaml.safe_dump(environment, default_flow_style=False)
        path = os.path.join(tmp_dir, constants.PLAN_ENVIRONMENT)

        with open(path, 'w') as f:
            f.write(yaml_string)

    def _create_and_upload_tarball(self, swift, tmp_dir):
        """Create a tarball containing the tmp_dir and upload it to Swift."""
        tarball_name = '%s.tar.gz' % self.plan
        headers = {'X-Delete-After': self.delete_after}

        # make sure the root container which holds all plan exports exists
        try:
            swift.get_container(self.exports_container)
        except swiftexceptions.ClientException:
            swift.put_container(self.exports_container)

        with tempfile.NamedTemporaryFile() as tmp_tarball:
            tarball.create_tarball(tmp_dir, tmp_tarball.name)

            swift.put_object(self.exports_container, tarball_name, tmp_tarball,
                             headers=headers)

    def run(self):
        swift = self.get_object_client()
        mistral = self.get_workflow_client()
        tmp_dir = tempfile.mkdtemp()

        try:
            self._download_templates(swift, tmp_dir)
            self._generate_plan_env_file(mistral, tmp_dir)
            self._create_and_upload_tarball(swift, tmp_dir)
        except swiftexceptions.ClientException as err:
            msg = "Error attempting an operation on container: %s" % err
            return mistral_workflow_utils.Result(error=msg)
        except mistralclient_base.APIException:
            msg = ("The Mistral environment %s could not be found."
                   % self.plan)
            return mistral_workflow_utils.Result(error=msg)
        except (OSError, IOError) as err:
            msg = "Error while writing file: %s" % err
            return mistral_workflow_utils.Result(error=msg)
        except processutils.ProcessExecutionError as err:
            msg = "Error while creating a tarball: %s" % err
            return mistral_workflow_utils.Result(error=msg)
        except Exception as err:
            msg = "Error exporting plan: %s" % err
            return mistral_workflow_utils.Result(error=msg)
        finally:
            shutil.rmtree(tmp_dir)
