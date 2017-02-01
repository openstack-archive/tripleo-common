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
from mistral.workflow import utils as mistral_workflow_utils
from mistralclient.api import base as mistralclient_api
from oslo_concurrency.processutils import ProcessExecutionError

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import passwords as password_utils
from tripleo_common.utils import validations as utils


class GetPubkeyAction(base.TripleOAction):

    def run(self):
        mc = self.get_workflow_client()
        try:
            env = mc.environments.get('ssh_keys')
            public_key = env.variables['public_key']
        except Exception:
            ssh_key = password_utils.create_ssh_keypair()
            public_key = ssh_key['public_key']

            workflow_env = {
                'name': 'ssh_keys',
                'description': 'SSH keys for TripleO validations',
                'variables': ssh_key
            }
            mc.environments.create(**workflow_env)

        return public_key


class Enabled(base.TripleOAction):
    """Indicate whether the validations have been enabled."""

    def _validations_enabled(self):
        """Detect whether the validations are enabled on the undercloud."""
        mistral = self.get_workflow_client()
        try:
            # NOTE: the `ssh_keys` environment is created by
            # instack-undercloud only when the validations are enabled on the
            # undercloud (or when they're installed manually). Therefore, we
            # can check for its presence here:
            mistral.environments.get('ssh_keys')
            return True
        except Exception:
            return False

    def run(self):
        return_value = {'stderr': ''}
        if self._validations_enabled():
            return_value['stdout'] = 'Validations are enabled'
            mistral_result = {"data": return_value}
        else:
            return_value['stdout'] = 'Validations are disabled'
            mistral_result = {"error": return_value}
        return mistral_workflow_utils.Result(**mistral_result)


class ListValidationsAction(base.TripleOAction):
    """Return a set of TripleO validations"""
    def __init__(self, groups=None):
        super(ListValidationsAction, self).__init__()
        self.groups = groups

    def run(self):
        return utils.load_validations(groups=self.groups)


class ListGroupsAction(base.TripleOAction):
    """Return a set of TripleO validation groups"""

    def run(self):
        validations = utils.load_validations()
        return {
            group for validation in validations
            for group in validation['groups']
        }


class RunValidationAction(base.TripleOAction):
    """Run the given validation"""
    def __init__(self, validation, plan=constants.DEFAULT_CONTAINER_NAME):
        super(RunValidationAction, self).__init__()
        self.validation = validation
        self.plan = plan

    def run(self):
        mc = self.get_workflow_client()
        identity_file = None
        try:
            env = mc.environments.get('ssh_keys')
            private_key = env.variables['private_key']
            identity_file = utils.write_identity_file(private_key)

            stdout, stderr = utils.run_validation(self.validation,
                                                  identity_file,
                                                  self.plan)
            return_value = {'stdout': stdout, 'stderr': stderr}
            mistral_result = {"data": return_value}
        except mistralclient_api.APIException as e:
            return_value = {'stdout': '', 'stderr': e.error_message}
            mistral_result = {"error": return_value}
        except ProcessExecutionError as e:
            return_value = {'stdout': e.stdout, 'stderr': e.stderr}
            # Indicates to Mistral there was a failure
            mistral_result = {"error": return_value}
        finally:
            if identity_file:
                utils.cleanup_identity_file(identity_file)
        return mistral_workflow_utils.Result(**mistral_result)


class CheckBootImagesAction(base.TripleOAction):
    """Validate boot images"""

    # TODO(bcrochet): The validation actions are temporary. This logic should
    #                 move to the tripleo-validations project eventually.
    def __init__(self, images,
                 deploy_kernel_name=constants.DEFAULT_DEPLOY_KERNEL_NAME,
                 deploy_ramdisk_name=constants.DEFAULT_DEPLOY_RAMDISK_NAME):
        super(CheckBootImagesAction, self).__init__()
        self.images = images
        self.deploy_kernel_name = deploy_kernel_name
        self.deploy_ramdisk_name = deploy_ramdisk_name

    def run(self):
        messages = []
        kernel_id = self._check_for_image(self.deploy_kernel_name, messages)
        ramdisk_id = self._check_for_image(self.deploy_ramdisk_name, messages)

        return_value = {
            'kernel_id': kernel_id,
            'ramdisk_id': ramdisk_id,
            'errors': messages,
            'warnings': []
        }

        if messages:
            mistral_result = mistral_workflow_utils.Result(error=return_value)
        else:
            mistral_result = mistral_workflow_utils.Result(data=return_value)

        return mistral_result

    def _check_for_image(self, name, messages):
        multiple_message = ("Please make sure there is only one image named "
                            "'{}' in glance.")
        missing_message = ("No image with the name '{}' found - make sure you "
                           "have uploaded boot images.")

        image_id = None
        found_images = [item['id'] for item in self.images
                        if item['name'] == name]
        if len(found_images) > 1:
            messages.append(multiple_message.format(name))
        elif len(found_images) == 0:
            messages.append(missing_message.format(name))
        else:
            image_id = found_images[0]

        return image_id


class CheckFlavorsAction(base.TripleOAction):
    """Validate and collect nova flavors in use.

    Ensure that selected flavors (--ROLE-flavor) are valid in nova.
    Issue a warning if local boot is not set for a flavor.
    """

    # TODO(bcrochet): The validation actions are temporary. This logic should
    #                 move to the tripleo-validations project eventually.
    def __init__(self, flavors, roles_info):
        super(CheckFlavorsAction, self).__init__()
        self.flavors = flavors
        self.roles_info = roles_info

    def run(self):
        """Validate and collect nova flavors in use.

        Ensure that selected flavors (--ROLE-flavor) are valid in nova.
        Issue a warning if local boot is not set for a flavor.

        :returns: dictionary flavor name -> (flavor object, scale)
        """
        flavors = {f['name']: f for f in self.flavors}
        result = {}
        warnings = []
        errors = []

        message = "Flavor '{1}' provided for the role '{0}', does not exist"

        for target, (flavor_name, scale) in self.roles_info.items():
            if flavor_name is None or not scale:
                continue

            old_flavor_name, old_scale = result.get(flavor_name, (None, None))

            if old_flavor_name:
                result[flavor_name] = (old_flavor_name, old_scale + scale)
            else:
                flavor = flavors.get(flavor_name)

                if flavor:
                    if flavor.get('capabilities:boot_option', '') == 'netboot':
                        warnings.append(
                            'Flavor %s "capabilities:boot_option" is set to '
                            '"netboot". Nodes will PXE boot from the ironic '
                            'conductor instead of using a local bootloader. '
                            'Make sure that enough nodes are marked with the '
                            '"boot_option" capability set to "netboot".'
                            % flavor_name)

                    result[flavor_name] = (flavor, scale)
                else:
                    errors.append(message.format(target, flavor_name))

        return_value = {
            'flavors': result,
            'errors': errors,
            'warnings': warnings,
        }
        if errors:
            mistral_result = {'error': return_value}
        else:
            mistral_result = {'data': return_value}

        return mistral_workflow_utils.Result(**mistral_result)
