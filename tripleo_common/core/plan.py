# Copyright 2015 Red Hat, Inc.
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
import yaml

from heatclient import exc as heatexceptions
import six
from swiftclient import exceptions as swiftexceptions

from tripleo_common.core import exception
from tripleo_common.utils import meta
from tripleo_common.utils import templates

LOG = logging.getLogger(__name__)


class PlanManager(object):

    def __init__(self, plan_storage_backend, heatclient):
        # TODO(rbrady) add code to create a storage backend based on config
        # so the API can send a string representing a backend type and any
        # client objects needed by the backend type
        self.plan_store = plan_storage_backend
        self.heatclient = heatclient

    def create_plan(self, plan_name, plan_files):
        """Creates a plan to store templates

        Creates a plan by creating a container matching plan_name, and
        import given plan_files into it.  The plan files is a dictionary
        where the keys are filenames and the values are file contents.

        :param plan_name: The name of the plan to use as the container name
        :type plan_name: str
        :param plan_files: The files to import into the container.
        :type plan_files: dict
        """

        # create container with versioning
        try:
            self.plan_store.create(plan_name)
        except Exception:
            LOG.exception("Error creating plan.")
            raise

        plan_files = meta.add_file_metadata(plan_files)
        return self.update_plan(plan_name, plan_files)

    def delete_plan(self, plan_name):
        """Deletes a plan and associated files

        Deletes a plan by deleting the container matching plan_name. It
        will not delete the plan if a stack exists with the same name.

        Raises StackInUseError if a stack with the same name as plan_name
        exists.

        :param plan_name: The name of the container to delete
        :type plan_name: str
        """
        # heat throws HTTPNotFound if the stack is not found
        try:
            stack = self.heatclient.stacks.get(plan_name)
            if stack is not None:
                raise exception.StackInUseError(name=plan_name)
        except heatexceptions.HTTPNotFound:
            try:
                self.plan_store.delete(plan_name)
            except swiftexceptions.ClientException as ce:
                LOG.exception("Swift error deleting plan.")
                if ce.http_status == 404:
                    six.raise_from(exception.PlanDoesNotExistError(
                        name=plan_name), ce)
            except Exception:
                LOG.exception("Error deleting plan.")
                raise

    def delete_file(self, plan_name, filename):
        """Deletes file in a plan container

        :param plan_name: The name of the plan to use as the container name
        :type plan_name: str
        :param filename: The file to delete from the container.
        :type filename: str
        """
        try:
            self.plan_store.delete_file(plan_name, filename)
        except swiftexceptions.ClientException as ce:
            LOG.exception("Swift error deleting file.")
            if ce.http_status == 404:
                six.raise_from(exception.FileDoesNotExistError(
                    name=filename), ce)
        except Exception:
            LOG.exception("Error deleting file from plan.")
            raise

    def delete_temporary_environment(self, plan_name):
        """Deletes the temporary environment files

        The temporary environment is the combination of deployment parameters
        and selected environment information

        :param plan_name: The name of the plan to use as the container name
        :type plan_name: str
        """
        plan = self.get_plan(plan_name)
        for item in {k: v for (k, v) in plan.files.items() if
                     v.get('meta', {}).get('file-type') == 'temp-environment'}:
            self.plan_store.delete_file(plan_name, item)

    def get_plan(self, plan_name):
        """Retrieves the Heat templates and environment file

        Retrieves the files from the container matching plan_name.

        :param plan_name: The name of the plan to retrieve files for.
        :type plan_name: str
        :rtype dict
        """

        try:
            return self.plan_store.get(plan_name)
        except swiftexceptions.ClientException as ce:
            LOG.exception("Swift error retrieving plan.")
            if ce.http_status == 404:
                six.raise_from(exception.PlanDoesNotExistError(
                    name=plan_name), ce)
        except Exception:
            LOG.exception("Error retrieving plan.")
            raise

    def get_plan_list(self):
        """Gets a list of containers that store plans

        Gets a list of containers that contain metadata with the key of
        X-Container-Meta-Usage-Tripleo and value or 'plan'.

        :return: a list of strings containing plan names
        """
        try:
            return self.plan_store.list()
        except Exception:
            LOG.exception("Error retrieving plan list.")
            raise

    def get_deployment_parameters(self, plan_name):
        """Determine available deployment parameters

        :param plan_name: The name of the plan and container name
        """

        plan = self.get_plan(plan_name)
        template, environment, files = templates.process_plan_data(plan.files)
        try:
            params = self.heatclient.stacks.validate(
                template=template,
                files=files,
                environment=environment,
                show_nested=True)
        except heatexceptions.HTTPBadRequest as exc:
            six.raise_from(exception.HeatValidationFailedError(msg=exc), exc)

        return params

    def update_deployment_parameters(self, plan_name, deployment_parameters):
        """Update the deployment parameters

        :param plan_name: The name of the plan and container name
        :type plan_name: str
        :param deployment_parameters: dictionary of deployment parameters
        :type deployment_parameters: dict
        """

        plan = self.get_plan(plan_name)
        deployment_params_file = 'environments/deployment_parameters.yaml'
        # Make sure the dict has the expected environment file format.
        if not deployment_parameters.get('parameter_defaults'):
            deployment_parameters = {
                'parameter_defaults': deployment_parameters
            }
        # pop the deployment params temporary environment file from the plan
        # so it's not included in the validation call.  If the stack is valid
        # the deployment params temporary environment file is overwritten
        if deployment_params_file in plan.files:
            plan.files.pop(deployment_params_file)
        # Update deployment params and validate through heat API.
        template, environment, files = templates.process_plan_data(plan.files)
        environment = templates.deep_update(environment, deployment_parameters)
        try:
            self.heatclient.stacks.validate(
                template=template,
                files=files,
                environment=environment,
                show_nested=True)
        except heatexceptions.HTTPBadRequest as exc:
            six.raise_from(exception.HeatValidationFailedError(msg=exc), exc)

        env = yaml.safe_dump(deployment_parameters, default_flow_style=False)
        plan.files[deployment_params_file] = {
            'contents': env,
            'meta': {
                'file-type': 'temp-environment',
            }
        }
        self.update_plan(plan_name, plan.files)

    def update_plan(self, plan_name, plan_files):
        """Updates files in a plan container

        :param plan_name: The name of the plan to use as the container name
        :type plan_name: str
        :param plan_files: The files to import into the container.
        :type plan_files: dict
        """

        try:
            self.plan_store.update(plan_name, plan_files)
        except swiftexceptions.ClientException as ce:
            LOG.exception("Swift error updating plan.")
            if ce.http_status == 404:
                six.raise_from(exception.PlanDoesNotExistError(
                    name=plan_name), ce)
        except Exception:
            LOG.exception("Error updating plan.")
            raise

        return self.get_plan(plan_name)

    def validate_plan(self, plan_name):
        """Validate Plan

        This private method provides validations to ensure a plan
        meets the proper criteria before allowed to persist in storage.

        :param plan_files: The files to import into the container.
        :type plan_files: dict
        :returns boolean
        """

        plan = self.get_plan(plan_name)
        # there can only be up to one root-template file in metadata
        rt = {k: v for (k, v) in plan.files.items()
              if v.get('meta', {}).get('file-type') == 'root-template'}
        if len(rt) > 1:
            raise exception.TooManyRootTemplatesError()

        # the plan needs to be validated with heat to ensure it conforms
        template, environment, files = templates.process_plan_data(plan.files)
        try:
            self.heatclient.stacks.validate(
                template=template,
                files=files,
                environment=environment,
                show_nested=True)
        except heatexceptions.HTTPBadRequest as exc:
            LOG.exception("Error validating the plan.")
            six.raise_from(exception.HeatValidationFailedError(msg=exc), exc)

        # no validation issues found
        return True
