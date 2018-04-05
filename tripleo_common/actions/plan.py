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
from operator import itemgetter
import shutil
import tempfile
import yaml

from heatclient import exc as heatexceptions
from mistral_lib import actions
from oslo_concurrency import processutils
import six
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common import exception
from tripleo_common.utils import plan as plan_utils
from tripleo_common.utils import roles as roles_utils
from tripleo_common.utils import swift as swiftutils
from tripleo_common.utils import tarball
from tripleo_common.utils.validations import pattern_validator


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

    def run(self, context):
        oc = self.get_object_client(context)

        # checks to see if a container has a valid name
        if not pattern_validator(constants.PLAN_NAME_PATTERN, self.container):
            message = ("Unable to create plan. The plan name must "
                       "only contain letters, numbers or dashes")
            return actions.Result(error=message)

        # checks to see if a container with that name exists
        if self.container in [container["name"] for container in
                              oc.get_account()[1]]:
            result_string = ("A container with the name %s already"
                             " exists.") % self.container
            return actions.Result(error=result_string)
        oc.put_container(self.container, headers=default_container_headers)


class ListPlansAction(base.TripleOAction):
    """Lists deployment plans

    This action lists all deployment plans residing in the undercloud.  A
    deployment plan consists of a container marked with metadata
    'x-container-meta-usage-tripleo'.
    """

    def run(self, context):
        # Plans consist of a container object marked with metadata to ensure it
        # isn't confused with another container
        plan_list = []
        oc = self.get_object_client(context)

        for item in oc.get_account()[1]:
            container = oc.get_container(item['name'])[0]
            if constants.TRIPLEO_META_USAGE_KEY in container.keys():
                plan_list.append(item['name'])
        return list(set(plan_list))


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

    def run(self, context):
        error_text = None
        # heat throws HTTPNotFound if the stack is not found
        try:
            stack = self.get_orchestration_client(context).stacks.get(
                self.container
            )
        except heatexceptions.HTTPNotFound:
            pass
        else:
            if stack is not None:
                raise exception.StackInUseError(name=self.container)

        try:
            swift = self.get_object_client(context)
            swiftutils.delete_container(swift, self.container)
            swiftutils.delete_container(swift,
                                        "%s-swift-rings" % self.container)
        except swiftexceptions.ClientException as ce:
            LOG.exception("Swift error deleting plan.")
            error_text = ce.msg
        except Exception as err:
            LOG.exception("Error deleting plan.")
            error_text = six.text_type(err)

        if error_text:
            return actions.Result(error=error_text)


class ListRolesAction(base.TripleOAction):
    """Returns a deployment plan's roles

    Parses roles_data.yaml and returns the names of all available roles.

    :param container: name of the Swift container / plan name
    :param detail: if false(default), displays role names only.  if true,
                   returns all roles data
    :return: list of roles in the container's deployment plan
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME,
                 role_file_name=constants.OVERCLOUD_J2_ROLES_NAME,
                 detail=False):
        super(ListRolesAction, self).__init__()
        self.container = container
        self.role_file_name = role_file_name
        self.detail = detail

    def run(self, context):
        try:
            swift = self.get_object_client(context)
            roles_data = yaml.safe_load(swift.get_object(
                self.container, self.role_file_name)[1])
        except Exception as err:
            err_msg = ("Error retrieving roles data from deployment plan: %s"
                       % err)
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        if self.detail:
            return roles_data
        else:
            return [role['name'] for role in roles_data]


class ExportPlanAction(base.TripleOAction):
    """Exports a deployment plan

    This action exports a deployment plan with a given name. The plan
    templates are downloaded from the Swift container, packaged up in a tarball
    and uploaded to Swift.
    """

    def __init__(self, plan, delete_after, exports_container):
        super(ExportPlanAction, self).__init__()
        self.plan = plan
        self.delete_after = delete_after
        self.exports_container = exports_container

    def run(self, context):
        swift = self.get_object_client(context)
        swift_service = self.get_object_service(context)

        tmp_dir = tempfile.mkdtemp()
        tarball_name = '%s.tar.gz' % self.plan

        try:
            swiftutils.download_container(swift, self.plan, tmp_dir)
            swiftutils.create_and_upload_tarball(
                swift_service, tmp_dir, self.exports_container, tarball_name,
                delete_after=self.delete_after)
        except swiftexceptions.ClientException as err:
            msg = "Error attempting an operation on container: %s" % err
            return actions.Result(error=msg)
        except (OSError, IOError) as err:
            msg = "Error while writing file: %s" % err
            return actions.Result(error=msg)
        except processutils.ProcessExecutionError as err:
            msg = "Error while creating a tarball: %s" % err
            return actions.Result(error=msg)
        except Exception as err:
            msg = "Error exporting plan: %s" % err
            return actions.Result(error=msg)
        finally:
            shutil.rmtree(tmp_dir)


class UpdatePlanFromDirAction(base.TripleOAction):
    """Updates a plan and associated files

    Updates a plan by comparing the current files with the new ones
    provided:
        Updates only new files from the plan
        Add new files from the plan

    :param container: name of the Swift container / plan name
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME,
                 templates_dir=constants.DEFAULT_TEMPLATES_PATH):
        super(UpdatePlanFromDirAction, self).__init__()
        self.container = container
        self.templates_dir = templates_dir

    def run(self, context):
        try:
            swift = self.get_object_client(context)
            # Upload template dir to tmp container
            container_tmp = '%s-tmp' % self.container
            with tempfile.NamedTemporaryFile() as tmp_tarball:
                tarball.create_tarball(self.templates_dir, tmp_tarball.name)
                tarball.tarball_extract_to_swift_container(
                    swift,
                    tmp_tarball.name,
                    container_tmp)
            # Get all new templates:
            new_templates = swift.get_object(container_tmp,
                                             '')[1].splitlines()
            old_templates = swift.get_object(self.container,
                                             '')[1].splitlines()
            exclude_user_data = [constants.PLAN_ENVIRONMENT,
                                 constants.OVERCLOUD_J2_ROLES_NAME,
                                 constants.OVERCLOUD_J2_NETWORKS_NAME,
                                 constants.OVERCLOUD_J2_EXCLUDES]
            # Update the old container
            for new in new_templates:
                # if doesn't exist, push it:
                if new not in old_templates:
                    swift.put_object(
                        self.container,
                        new,
                        swift.get_object(container_tmp, new)[1])
                else:
                    content_new = swift.get_object(container_tmp, new)
                    content_old = swift.get_object(self.container, new)
                    if (not content_new == content_old and
                       new not in exclude_user_data):
                        swift.put_object(
                            self.container,
                            new,
                            swift.get_object(container_tmp, new)[1])
        except swiftexceptions.ClientException as err:
            msg = "Error attempting an operation on container: %s" % err
            LOG.exception(msg)
            return actions.Result(error=msg)
        except Exception as err:
            msg = "Error while updating plan: %s" % err
            LOG.exception(msg)
            return actions.Result(error=msg)


class UpdatePlanEnvironmentAction(base.TripleOAction):
    """Updates the plan environment values

    Updates a plan environment values with the given parameters:
        Add new parameter
        Delete parameter

    :param parameter: key value of the parameter to add or delete
    :param value: value of the parameter to add or delete
    :param delete: True if the parameter should be deleted from the env
    :param env_key: environment key that should be one of the keys present
                    in the plan environment dictionary:
                         'passwords',
                         'description',
                         'parameter_defaults',
                         'environments',
                         'version',
                         'template',
                         'resource_registry',
                         'name'
    :param container: name of the Swift container / plan name
    """

    def __init__(self, parameter, env_key, value=None, delete=False,
                 container=constants.DEFAULT_CONTAINER_NAME):
        super(UpdatePlanEnvironmentAction, self).__init__()
        self.container = container
        self.parameter = parameter
        self.value = value
        self.delete = delete
        self.env_key = env_key

    def run(self, context):
        try:
            swift = self.get_object_client(context)
            plan_env = plan_utils.get_env(swift, self.container)
            if self.env_key in plan_env.keys():
                if self.delete:
                    try:
                        plan_env[self.env_key].pop(self.parameter)
                    except KeyError:
                        pass
                else:
                    plan_env[self.env_key].update({self.parameter: self.value})
            else:
                msg = "The environment key doesn't exist: %s" % self.env_key
                return actions.Result(error=msg)
        except swiftexceptions.ClientException as err:
            msg = "Error attempting an operation on container: %s" % err
            return actions.Result(error=msg)
        except Exception as err:
            msg = "Error while updating plan: %s" % err
            return actions.Result(error=msg)


class UpdateNetworksAction(base.TripleOAction):
    def __init__(self, networks, current_networks, replace_all=False):
        super(UpdateNetworksAction, self).__init__()
        self.networks = networks
        self.current_networks = current_networks
        self.replace_all = replace_all

    def run(self, context):
        network_data_to_save = self.networks or []

        # if replace_all flag is true, discard current networks and save input
        # if replace_all flag is false, merge input into current networks
        if not self.replace_all:
            # merge the networks_data and the network_input into networks
            # to be saved
            network_data_to_save = [net for net in {
                x['name']: x for x in
                self.current_networks + self.networks
            }.values()]

        return actions.Result(data={'network_data': network_data_to_save})


class ValidateRolesDataAction(base.TripleOAction):
    """Validates Roles Data

    Validates the format of input (verify that each role in input has the
    required attributes set. see README in roles directory in t-h-t),
    validates that roles in input exist in roles directory in deployment plan
    """

    def __init__(self, roles, available_roles,
                 container=constants.DEFAULT_CONTAINER_NAME):
        super(ValidateRolesDataAction, self).__init__()
        self.container = container
        self.roles = roles
        self.available_roles = available_roles

    def run(self, context):
        err_msg = ""
        # validate roles in input exist in roles directory in t-h-t
        try:
            roles_utils.check_role_exists(
                [role['name'] for role in self.available_roles],
                [role['name'] for role in self.roles])
        except Exception as chk_err:
            err_msg = str(chk_err)

        # validate role yaml
        for role in self.roles:
            try:
                roles_utils.validate_role_yaml(yaml.safe_dump([role]))
            except exception.RoleMetadataError as rme:
                if 'name' in role:
                    err_msg += "\n%s for %s" % (str(rme), role['name'])
                else:
                    err_msg += "\n%s" % str(rme)

        if err_msg:
            return actions.Result(error=err_msg)
        return actions.Result(data=True)


class UpdateRolesAction(base.TripleOAction):
    """Updates roles_data.yaml object in plan with given roles.

    :param roles: role input data (json)
    :param current_roles: data from roles_data.yaml file in plan (json)
    :param replace_all: boolean value indicating if input roles should merge
    with or replace data from roles_data.yaml.  Defaults to False (merge)
    :param container: name of the Swift container / plan name
    """

    def __init__(self, roles, current_roles, replace_all=False,
                 container=constants.DEFAULT_CONTAINER_NAME):
        super(UpdateRolesAction, self).__init__()
        self.container = container
        self.roles = roles
        self.current_roles = current_roles
        self.replace_all = replace_all

    def run(self, context):
        role_data_to_save = self.roles

        # if replace_all flag is true, discard current roles and save input
        # if replace_all flag is false, merge input into current roles
        if not self.replace_all:
            # merge the roles_data and the role_input into roles to be saved
            role_data_to_save = [role for role in {
                x['name']: x for x in
                self.current_roles + self.roles
            }.values()]

        # ensure required primary tag exists in roles to be saved
        primary = [role for role in role_data_to_save if
                   'tags' in role and 'primary' in role['tags']]
        if len(primary) < 1:
            # throw error
            raise exception.RoleMetadataError("At least one role must contain"
                                              " a 'primary' tag.")

        # sort the data to have a predictable result
        save_roles = sorted(role_data_to_save, key=itemgetter('name'),
                            reverse=True)
        return actions.Result(data={'roles': save_roles})


class GatherRolesAction(actions.Action):
    """Gather role definitions

    Check each role name from the input, check if it exists in
    roles_data.yaml, if yes, use that role definition, if not, get the
    role definition from roles directory. Return the gathered role
    definitions.
    """

    def __init__(self, role_names, current_roles, available_roles):
        super(GatherRolesAction, self).__init__()
        self.role_names = role_names
        self.current_roles = current_roles
        self.available_roles = available_roles

    def run(self, context):
        err_msgs = []
        # merge the two lists of dicts in the proper order.  last in wins, so
        # a current role shall be favored over an available role.
        gathered_roles = [role for role in {
            x['name']: x for x in self.available_roles + self.current_roles
        }.values() if role['name'] in self.role_names]

        if err_msgs:
            return actions.Result(error="/n".join(err_msgs))

        return actions.Result(data={'gathered_roles': gathered_roles})


class RemoveNoopDeployStepAction(base.TripleOAction):
    """Remove all the pre, post and deploy step in the plan-environment.

    :param container: name of the Swift container / plan name
    """

    def __init__(self, container=constants.DEFAULT_CONTAINER_NAME):
        super(RemoveNoopDeployStepAction, self).__init__()
        self.container = container

    def run(self, context):
        # get the stack. Error if doesn't exist
        heat = self.get_orchestration_client(context)
        try:
            stack = heat.stacks.get(self.container)
        except heatexceptions.HTTPNotFound:
            msg = "Error retrieving stack: %s" % self.container
            LOG.exception(msg)
            return actions.Result(error=msg)

        swift = self.get_object_client(context)
        plan_env = plan_utils.get_env(swift, self.container)

        # Get output and check if DeployStep are None
        steps = ['OS::TripleO::DeploymentSteps']
        for output in stack.to_dict().get('outputs', {}):
            if output['output_key'] == 'RoleData':
                for role in output['output_value']:
                    steps.append("OS::TripleO::Tasks::%sPreConfig" % role)
                    steps.append("OS::TripleO::Tasks::%sPostConfig" % role)
        # Remove noop Steps
        for step in steps:
            if step in plan_env.get('resource_registry', {}):
                if plan_env['resource_registry'][step] == 'OS::Heat::None':
                    plan_env['resource_registry'].pop(step)
        # Push plan_env
        plan_utils.put_env(swift, plan_env)
