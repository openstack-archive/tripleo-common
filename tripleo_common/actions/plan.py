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


LOG = logging.getLogger(__name__)


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
                self.container, resolve_outputs=False)
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
            swiftutils.delete_container(swift,
                                        "%s-messages" % self.container)
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

    DEPRECATED

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
            return roles_utils.get_roles_from_plan(
                swift, container=self.container,
                role_file_name=self.role_file_name,
                detail=self.detail)
        except Exception as err:
            return actions.Result(error=six.text_type(err))


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

        # Get output and check if DeployStep are None
        removals = ['OS::TripleO::DeploymentSteps']
        for output in stack.to_dict().get('outputs', {}):
            if output['output_key'] == 'RoleData':
                for role in output['output_value']:
                    removals.append("OS::TripleO::Tasks::%sPreConfig" % role)
                    removals.append("OS::TripleO::Tasks::%sPostConfig" % role)

        plan_env = plan_utils.get_env(swift, self.container)
        self.remove_noops_from_env(removals, plan_env)
        plan_utils.put_env(swift, plan_env)

        user_env = plan_utils.get_user_env(swift, self.container)
        self.remove_noops_from_env(removals, user_env)
        plan_utils.put_user_env(swift, self.container, user_env)

    def remove_noops_from_env(self, removals, env):
        # Remove noop Steps
        for rm in removals:
            if rm in env.get('resource_registry', {}):
                if env['resource_registry'][rm] == 'OS::Heat::None':
                    env['resource_registry'].pop(rm)
