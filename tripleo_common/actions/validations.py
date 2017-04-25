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
from mistral_lib import actions
from mistralclient.api import base as mistralclient_api
from oslo_concurrency.processutils import ProcessExecutionError

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import nodes as nodeutils
from tripleo_common.utils import passwords as password_utils
from tripleo_common.utils import validations as utils


class GetSshKeyAction(base.TripleOAction):

    def run(self, context):
        mc = self.get_workflow_client(context)
        try:
            env = mc.environments.get('ssh_keys')
            p_key = env.variables[self.key_type]
        except Exception:
            ssh_key = password_utils.create_ssh_keypair()
            p_key = ssh_key[self.key_type]

            workflow_env = {
                'name': 'ssh_keys',
                'description': 'SSH keys for TripleO validations',
                'variables': ssh_key
            }
            mc.environments.create(**workflow_env)

        return p_key


class GetPubkeyAction(GetSshKeyAction):

    key_type = 'public_key'


class GetPrivkeyAction(GetSshKeyAction):

    key_type = 'private_key'


class Enabled(base.TripleOAction):
    """Indicate whether the validations have been enabled."""

    def _validations_enabled(self, context):
        """Detect whether the validations are enabled on the undercloud."""
        mistral = self.get_workflow_client(context)
        try:
            # NOTE: the `ssh_keys` environment is created by
            # instack-undercloud only when the validations are enabled on the
            # undercloud (or when they're installed manually). Therefore, we
            # can check for its presence here:
            mistral.environments.get('ssh_keys')
            return True
        except Exception:
            return False

    def run(self, context):
        return_value = {'stderr': ''}
        if self._validations_enabled(context):
            return_value['stdout'] = 'Validations are enabled'
            mistral_result = {"data": return_value}
        else:
            return_value['stdout'] = 'Validations are disabled'
            mistral_result = {"error": return_value}
        return actions.Result(**mistral_result)


class ListValidationsAction(base.TripleOAction):
    """Return a set of TripleO validations"""
    def __init__(self, groups=None):
        super(ListValidationsAction, self).__init__()
        self.groups = groups

    def run(self, context):
        return utils.load_validations(groups=self.groups)


class ListGroupsAction(base.TripleOAction):
    """Return a set of TripleO validation groups"""

    def run(self, context):
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

    def run(self, context):
        mc = self.get_workflow_client(context)
        identity_file = None
        try:
            env = mc.environments.get('ssh_keys')
            private_key = env.variables['private_key']
            identity_file = utils.write_identity_file(private_key)

            stdout, stderr = utils.run_validation(self.validation,
                                                  identity_file,
                                                  self.plan,
                                                  context)
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
        return actions.Result(**mistral_result)


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

    def run(self, context):
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
            mistral_result = actions.Result(error=return_value)
        else:
            mistral_result = actions.Result(data=return_value)

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
    def __init__(self, roles_info):
        super(CheckFlavorsAction, self).__init__()
        self.roles_info = roles_info

    def run(self, context):
        """Validate and collect nova flavors in use.

        Ensure that selected flavors (--ROLE-flavor) are valid in nova.
        Issue a warning if local boot is not set for a flavor.

        :returns: dictionary flavor name -> (flavor object, scale)
        """
        compute_client = self.get_compute_client(context)
        flavors = {f.name: {'name': f.name, 'keys': f.get_keys()}
                   for f in compute_client.flavors.list()}

        result = {}
        warnings = []
        errors = []

        message = "Flavor '{1}' provided for the role '{0}', does not exist"
        warning_message = (
            'Flavor {0} "capabilities:boot_option" is set to '
            '"netboot". Nodes will PXE boot from the ironic '
            'conductor instead of using a local bootloader. '
            'Make sure that enough nodes are marked with the '
            '"boot_option" capability set to "netboot".')

        for target, (flavor_name, scale) in self.roles_info.items():
            if flavor_name is None or not scale:
                continue

            old_flavor_name, old_scale = result.get(flavor_name, (None, None))

            if old_flavor_name:
                result[flavor_name] = (old_flavor_name, old_scale + scale)
            else:
                flavor = flavors.get(flavor_name)

                if flavor:
                    keys = flavor.get('keys', None)
                    if keys:
                        if keys.get('capabilities:boot_option', '') \
                                == 'netboot':
                            warnings.append(
                                warning_message.format(flavor_name))

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

        return actions.Result(**mistral_result)


class CheckNodeBootConfigurationAction(base.TripleOAction):
    """Check the boot configuration of the baremetal nodes"""

    # TODO(bcrochet): The validation actions are temporary. This logic should
    #                 move to the tripleo-validations project eventually.
    def __init__(self, node, kernel_id, ramdisk_id):
        super(CheckNodeBootConfigurationAction, self).__init__()

        self.node = node
        self.kernel_id = kernel_id
        self.ramdisk_id = ramdisk_id

    def run(self, context):
        warnings = []
        errors = []
        message = ("Node {uuid} has an incorrectly configured "
                   "{property}. Expected \"{expected}\" but got "
                   "\"{actual}\".")
        if self.node['driver_info'].get('deploy_ramdisk') != self.ramdisk_id:
            errors.append(message.format(
                uuid=self.node['uuid'],
                property='driver_info/deploy_ramdisk',
                expected=self.ramdisk_id,
                actual=self.node['driver_info'].get('deploy_ramdisk')
            ))
        if self.node['driver_info'].get('deploy_kernel') != self.kernel_id:
            errors.append(message.format(
                uuid=self.node['uuid'],
                property='driver_info/deploy_kernel',
                expected=self.kernel_id,
                actual=self.node['driver_info'].get('deploy_kernel')
            ))
        capabilities = nodeutils.capabilities_to_dict(
            self.node['properties'].get('capabilities', ''))
        if capabilities.get('boot_option') != 'local':
            boot_option_message = ("Node {uuid} is not configured to use "
                                   "boot_option:local in capabilities. It "
                                   "will not be used for deployment with "
                                   "flavors that require boot_option:local.")

            warnings.append(boot_option_message.format(uuid=self.node['uuid']))

        return_value = {
            'errors': errors,
            'warnings': warnings
        }
        if errors:
            mistral_result = {'error': return_value}
        else:
            mistral_result = {'data': return_value}

        return actions.Result(**mistral_result)


class VerifyProfilesAction(base.TripleOAction):
    """Verify that the profiles have enough nodes"""

    # TODO(bcrochet): The validation actions are temporary. This logic should
    #                 move to the tripleo-validations project eventually.
    def __init__(self, nodes, flavors):
        super(VerifyProfilesAction, self).__init__()

        self.nodes = nodes
        self.flavors = flavors

    def run(self, context):
        errors = []
        warnings = []

        bm_nodes = {node['uuid']: node for node in self.nodes
                    if node['provision_state'] in ('available', 'active')}

        if not bm_nodes:
            message = ('Error: There are no nodes in an available '
                       'or active state and with maintenance mode off.')
            return_value = {
                'errors': [message],
                'warnings': [],
            }
            return actions.Result(error=return_value)

        free_node_caps = {uu: self._node_get_capabilities(node)
                          for uu, node in bm_nodes.items()}

        profile_flavor_used = False
        for flavor_name, (flavor, scale) in self.flavors.items():
            if not scale:
                continue

            profile = None
            keys = flavor.get('keys')
            if keys:
                profile = keys.get('capabilities:profile')

            if not profile and len(self.flavors) > 1:
                message = ('Error: The {flavor} flavor has no profile '
                           'associated.\n'
                           'Recommendation: assign a profile with openstack '
                           'flavor set --property '
                           '"capabilities:profile"="PROFILE_NAME" {flavor}')

                errors.append(message.format(flavor=flavor_name))
                continue

            profile_flavor_used = True

            assigned_nodes = [uu for uu, caps in free_node_caps.items()
                              if caps.get('profile') == profile]
            required_count = scale - len(assigned_nodes)

            if required_count < 0:
                warnings.append('%d nodes with profile %s won\'t be used '
                                'for deployment now' % (-required_count,
                                                        profile))
                required_count = 0

            for uu in assigned_nodes:
                free_node_caps.pop(uu)

            if required_count > 0:
                message = ('Error: only {total} of {scale} requested ironic '
                           'nodes are tagged to profile {profile} (for flavor '
                           '{flavor}).\n'
                           'Recommendation: tag more nodes using openstack '
                           'baremetal node set --property "capabilities='
                           'profile:{profile},boot_option:local" <NODE ID>')
                errors.append(message.format(total=scale - required_count,
                                             scale=scale,
                                             profile=profile,
                                             flavor=flavor_name))

        nodes_without_profile = [uu for uu, caps in free_node_caps.items()
                                 if not caps.get('profile')]
        if nodes_without_profile and profile_flavor_used:
            warnings.append("There are %d ironic nodes with no profile that "
                            "will not be used: %s" % (
                                len(nodes_without_profile),
                                ', '.join(nodes_without_profile)))

        return_value = {
            'errors': errors,
            'warnings': warnings,
        }
        if errors:
            mistral_result = {'error': return_value}
        else:
            mistral_result = {'data': return_value}

        return actions.Result(**mistral_result)

    def _node_get_capabilities(self, node):
        """Get node capabilities."""
        return nodeutils.capabilities_to_dict(
            node['properties'].get('capabilities'))


class CheckNodesCountAction(base.TripleOAction):
    """Validate hypervisor statistics"""

    # TODO(bcrochet): The validation actions are temporary. This logic should
    #                 move to the tripleo-validations project eventually.
    def __init__(self, statistics, stack, associated_nodes, available_nodes,
                 parameters, default_role_counts):
        super(CheckNodesCountAction, self).__init__()
        self.statistics = statistics
        self.stack = stack
        self.associated_nodes = associated_nodes
        self.available_nodes = available_nodes
        self.parameters = parameters
        self.default_role_counts = default_role_counts

    def run(self, context):
        errors = []
        warnings = []

        requested_count = 0

        for param, default in self.default_role_counts.items():
            if self.stack:
                try:
                    current = int(self.stack['parameters'][param])
                except KeyError:
                    # We could be adding a new role on stack-update, so there's
                    # no assumption the parameter exists in the stack.
                    current = self.parameters.get(param, default)
                requested_count += self.parameters.get(param, current)
            else:
                requested_count += self.parameters.get(param, default)

        # We get number of nodes usable for the stack by getting already
        # used (associated) nodes and number of nodes which can be used
        # (not in maintenance mode).
        # Assumption is that associated nodes are part of the stack (only
        # one overcloud is supported).
        associated = len(self.associated_nodes)
        available = len(self.available_nodes)

        available_count = associated + available

        if requested_count > available_count:
            errors.append('Not enough baremetal nodes - available: %d, '
                          'requested: %d' %
                          (available_count, requested_count))

        if self.statistics['count'] < available_count:
            errors.append('Only %d nodes are exposed to Nova of %d requests. '
                          'Check that enough nodes are in "available" state '
                          'with maintenance mode off.' %
                          (self.statistics['count'], available_count))

        return_value = {
            'errors': errors,
            'warnings': warnings,
            'result': {
                'statistics': self.statistics,
                'enough_nodes': True,
                'requested_count': requested_count,
                'available_count': available_count,
            }
        }
        if errors:
            return_value['result']['enough_nodes'] = False
            mistral_result = {'error': return_value}
        else:
            mistral_result = {'data': return_value}

        return actions.Result(**mistral_result)
