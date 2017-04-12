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
import collections
import mock
from uuid import uuid4

from mistral.workflow import utils as mistral_workflow_utils
from oslo_concurrency.processutils import ProcessExecutionError

from tripleo_common.actions import validations
from tripleo_common import constants
from tripleo_common.tests import base
from tripleo_common.tests.utils import test_validations
from tripleo_common.utils import nodes as nodeutils


class GetPubkeyActionTest(base.TestCase):

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_run_existing_pubkey(self, get_workflow_client_mock):
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        environment = collections.namedtuple('environment', ['variables'])
        mistral.environments.get.return_value = environment(variables={
            'public_key': 'existing_pubkey'
        })
        action = validations.GetPubkeyAction()
        self.assertEqual('existing_pubkey', action.run())

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    @mock.patch('tripleo_common.utils.passwords.create_ssh_keypair')
    def test_run_no_pubkey(self, mock_create_keypair,
                           get_workflow_client_mock):
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        mistral.environments.get.side_effect = 'nope, sorry'
        mock_create_keypair.return_value = {
            'public_key': 'public_key',
            'private_key': 'private_key',
        }

        action = validations.GetPubkeyAction()
        self.assertEqual('public_key', action.run())


class Enabled(base.TestCase):

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_validations_enabled(self, get_workflow_client_mock):
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        mistral.environments.get.return_value = {}
        action = validations.Enabled()
        result = action._validations_enabled()
        self.assertEqual(result, True)

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_validations_disabled(self, get_workflow_client_mock):
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        mistral.environments.get.side_effect = Exception()
        action = validations.Enabled()
        result = action._validations_enabled()
        self.assertEqual(result, False)

    @mock.patch(
        'tripleo_common.actions.validations.Enabled._validations_enabled')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_success_with_validations_enabled(self, get_workflow_client_mock,
                                              validations_enabled_mock):
        validations_enabled_mock.return_value = True
        action = validations.Enabled()
        action_result = action.run()
        self.assertEqual(None, action_result.error)
        self.assertEqual('Validations are enabled',
                         action_result.data['stdout'])

    @mock.patch(
        'tripleo_common.actions.validations.Enabled._validations_enabled')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    def test_success_with_validations_disabled(self, get_workflow_client_mock,
                                               validations_enabled_mock):
        validations_enabled_mock.return_value = False
        action = validations.Enabled()
        action_result = action.run()
        self.assertEqual(None, action_result.data)
        self.assertEqual('Validations are disabled',
                         action_result.error['stdout'])


class ListValidationsActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.validations.load_validations')
    def test_run_default(self, mock_load_validations):
        mock_load_validations.return_value = 'list of validations'
        action = validations.ListValidationsAction()
        self.assertEqual('list of validations', action.run())
        mock_load_validations.assert_called_once_with(groups=None)

    @mock.patch('tripleo_common.utils.validations.load_validations')
    def test_run_groups(self, mock_load_validations):
        mock_load_validations.return_value = 'list of validations'
        action = validations.ListValidationsAction(groups=['group1',
                                                           'group2'])
        self.assertEqual('list of validations', action.run())
        mock_load_validations.assert_called_once_with(groups=['group1',
                                                              'group2'])


class ListGroupsActionTest(base.TestCase):

    @mock.patch('tripleo_common.utils.validations.load_validations')
    def test_run(self, mock_load_validations):
        mock_load_validations.return_value = [
            test_validations.VALIDATION_GROUPS_1_2_PARSED,
            test_validations.VALIDATION_GROUP_1_PARSED,
            test_validations.VALIDATION_WITH_METADATA_PARSED]
        action = validations.ListGroupsAction()
        self.assertEqual(set(['group1', 'group2']), action.run())
        mock_load_validations.assert_called_once_with()


class RunValidationActionTest(base.TestCase):

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    @mock.patch('tripleo_common.utils.validations.write_identity_file')
    @mock.patch('tripleo_common.utils.validations.cleanup_identity_file')
    @mock.patch('tripleo_common.utils.validations.run_validation')
    def test_run(self, mock_run_validation, mock_cleanup_identity_file,
                 mock_write_identity_file, get_workflow_client_mock):
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        environment = collections.namedtuple('environment', ['variables'])
        mistral.environments.get.return_value = environment(variables={
            'private_key': 'shhhh'
        })
        mock_write_identity_file.return_value = 'identity_file_path'
        mock_run_validation.return_value = 'output', 'error'
        action = validations.RunValidationAction('validation')
        expected = mistral_workflow_utils.Result(
            data={
                'stdout': 'output',
                'stderr': 'error'
            },
            error=None)
        self.assertEqual(expected, action.run())
        mock_write_identity_file.assert_called_once_with('shhhh')
        mock_run_validation.assert_called_once_with(
            'validation',
            'identity_file_path',
            constants.DEFAULT_CONTAINER_NAME)
        mock_cleanup_identity_file.assert_called_once_with(
            'identity_file_path')

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_workflow_client')
    @mock.patch('tripleo_common.utils.validations.write_identity_file')
    @mock.patch('tripleo_common.utils.validations.cleanup_identity_file')
    @mock.patch('tripleo_common.utils.validations.run_validation')
    def test_run_failing(self, mock_run_validation, mock_cleanup_identity_file,
                         mock_write_identity_file, get_workflow_client_mock):
        mistral = mock.MagicMock()
        get_workflow_client_mock.return_value = mistral
        environment = collections.namedtuple('environment', ['variables'])
        mistral.environments.get.return_value = environment(variables={
            'private_key': 'shhhh'
        })
        mock_write_identity_file.return_value = 'identity_file_path'
        mock_run_validation.side_effect = ProcessExecutionError(
            stdout='output', stderr='error')
        action = validations.RunValidationAction('validation')
        expected = mistral_workflow_utils.Result(
            data=None,
            error={
                'stdout': 'output',
                'stderr': 'error'
            })
        self.assertEqual(expected, action.run())
        mock_write_identity_file.assert_called_once_with('shhhh')
        mock_run_validation.assert_called_once_with(
            'validation',
            'identity_file_path',
            constants.DEFAULT_CONTAINER_NAME)
        mock_cleanup_identity_file.assert_called_once_with(
            'identity_file_path')


class TestCheckBootImagesAction(base.TestCase):
    def setUp(self):
        super(TestCheckBootImagesAction, self).setUp()
        self.images = [
            {'id': '67890', 'name': 'ramdisk'},
            {'id': '12345', 'name': 'kernel'},
        ]

    @mock.patch(
        'tripleo_common.actions.validations.CheckBootImagesAction'
        '._check_for_image')
    def test_run(self, mock_check_for_image):
        mock_check_for_image.side_effect = ['12345', '67890']
        expected = mistral_workflow_utils.Result(
            data={
                'kernel_id': '12345',
                'ramdisk_id': '67890',
                'warnings': [],
                'errors': []})
        action_args = {
            'images': self.images,
            'deploy_kernel_name': 'kernel',
            'deploy_ramdisk_name': 'ramdisk'
        }
        action = validations.CheckBootImagesAction(**action_args)
        self.assertEqual(expected, action.run())
        mock_check_for_image.assert_has_calls([
            mock.call('kernel', []),
            mock.call('ramdisk', [])
        ])

    def test_check_for_image_success(self):
        expected = '12345'
        action_args = {
            'images': self.images,
            'deploy_kernel_name': 'kernel',
            'deploy_ramdisk_name': 'ramdisk'
        }

        messages = mock.Mock()
        action = validations.CheckBootImagesAction(**action_args)
        self.assertEqual(expected, action._check_for_image('kernel', messages))
        messages.assert_not_called()

    def test_check_for_image_missing(self):
        expected = None
        deploy_kernel_name = 'missing'
        action_args = {
            'images': self.images,
            'deploy_kernel_name': deploy_kernel_name
        }
        expected_message = ("No image with the name '%s' found - make sure "
                            "you have uploaded boot images."
                            % deploy_kernel_name)

        messages = []
        action = validations.CheckBootImagesAction(**action_args)
        self.assertEqual(expected,
                         action._check_for_image(deploy_kernel_name, messages))
        self.assertEqual(1, len(messages))
        self.assertIn(expected_message, messages)

    def test_check_for_image_too_many(self):
        expected = None
        deploy_ramdisk_name = 'toomany'
        images = list(self.images)
        images.append({'id': 'abcde', 'name': deploy_ramdisk_name})
        images.append({'id': '45678', 'name': deploy_ramdisk_name})
        action_args = {
            'images': images,
            'deploy_ramdisk_name': deploy_ramdisk_name
        }
        expected_message = ("Please make sure there is only one image named "
                            "'%s' in glance." % deploy_ramdisk_name)

        messages = []
        action = validations.CheckBootImagesAction(**action_args)
        self.assertEqual(
            expected, action._check_for_image(deploy_ramdisk_name, messages))
        self.assertEqual(1, len(messages))
        self.assertIn(expected_message, messages)


class TestCheckFlavorsAction(base.TestCase):
    def setUp(self):
        super(TestCheckFlavorsAction, self).setUp()
        self.flavors = [
            {'name': 'flavor1', 'capabilities:boot_option': 'local'},
            {'name': 'flavor2', 'capabilities:boot_option': 'netboot'},
            {'name': 'flavor3'}
        ]

    def test_run_success(self):
        roles_info = {
            'role1': ('flavor1', 1),
        }

        expected = mistral_workflow_utils.Result(
            data={
                'flavors': {
                    'flavor1': (
                        {
                            'name': 'flavor1',
                            'capabilities:boot_option': 'local'
                        }, 1)
                },
                'warnings': [],
                'errors': [],
            }
        )

        action_args = {
            'flavors': self.flavors,
            'roles_info': roles_info
        }
        action = validations.CheckFlavorsAction(**action_args)
        self.assertEqual(expected, action.run())

    def test_run_boot_option_is_netboot(self):
        roles_info = {
            'role2': ('flavor2', 1),
            'role3': ('flavor3', 1),
        }

        expected = mistral_workflow_utils.Result(
            data={
                'flavors': {
                    'flavor2': (
                        {
                            'name': 'flavor2',
                            'capabilities:boot_option': 'netboot'
                        }, 1),
                    'flavor3': (
                        {
                            'name': 'flavor3',
                        }, 1),
                },
                'warnings': [
                    ('Flavor %s "capabilities:boot_option" is set to '
                     '"netboot". Nodes will PXE boot from the ironic '
                     'conductor instead of using a local bootloader. Make '
                     'sure that enough nodes are marked with the '
                     '"boot_option" capability set to "netboot".' % 'flavor2')
                ],
                'errors': []
            }
        )

        action_args = {
            'flavors': self.flavors,
            'roles_info': roles_info
        }
        action = validations.CheckFlavorsAction(**action_args)
        result = action.run()
        self.assertEqual(expected, result)

    def test_run_flavor_does_not_exist(self):
        roles_info = {
            'role4': ('does_not_exist', 1),
        }

        expected = mistral_workflow_utils.Result(
            error={
                'errors': [
                    "Flavor '%s' provided for the role '%s', does not "
                    "exist" % ('does_not_exist', 'role4')
                ],
                'warnings': [],
                'flavors': {},
            }
        )

        action_args = {
            'flavors': self.flavors,
            'roles_info': roles_info
        }
        action = validations.CheckFlavorsAction(**action_args)
        self.assertEqual(expected, action.run())


class TestCheckNodeBootConfigurationAction(base.TestCase):
    def setUp(self):
        super(TestCheckNodeBootConfigurationAction, self).setUp()
        self.kernel_id = '12345'
        self.ramdisk_id = '67890'
        self.node = {
            'uuid': '100f2cf6-06de-480e-a73e-6fdf6c9962b7',
            'driver_info': {
                'deploy_kernel': '12345',
                'deploy_ramdisk': '67890',
            },
            'properties': {
                'capabilities': 'boot_option:local',
            }
        }

    def test_run_success(self):
        expected = mistral_workflow_utils.Result(
            data={'errors': [], 'warnings': []}
        )

        action_args = {
            'node': self.node,
            'kernel_id': self.kernel_id,
            'ramdisk_id': self.ramdisk_id,
        }
        action = validations.CheckNodeBootConfigurationAction(**action_args)
        self.assertEqual(expected, action.run())

    def test_run_invalid_ramdisk(self):
        expected = mistral_workflow_utils.Result(
            error={
                'errors': [
                    'Node 100f2cf6-06de-480e-a73e-6fdf6c9962b7 has an '
                    'incorrectly configured driver_info/deploy_ramdisk. '
                    'Expected "67890" but got "98760".'
                ],
                'warnings': []})

        node = self.node.copy()
        node['driver_info']['deploy_ramdisk'] = '98760'
        action_args = {
            'node': node,
            'kernel_id': self.kernel_id,
            'ramdisk_id': self.ramdisk_id,
        }
        action = validations.CheckNodeBootConfigurationAction(**action_args)
        self.assertEqual(expected, action.run())

    def test_no_boot_option_local(self):
        expected = mistral_workflow_utils.Result(
            data={
                'errors': [],
                'warnings': [
                    'Node 100f2cf6-06de-480e-a73e-6fdf6c9962b7 is not '
                    'configured to use boot_option:local in capabilities. '
                    'It will not be used for deployment with flavors that '
                    'require boot_option:local.'
                ]
            }
        )

        node = self.node.copy()
        node['properties']['capabilities'] = 'boot_option:not_local'

        action_args = {
            'node': node,
            'kernel_id': self.kernel_id,
            'ramdisk_id': self.ramdisk_id,
        }

        action = validations.CheckNodeBootConfigurationAction(**action_args)
        self.assertEqual(expected, action.run())


class TestVerifyProfilesAction(base.TestCase):
    def setUp(self):
        super(TestVerifyProfilesAction, self).setUp()

        self.nodes = []
        self.flavors = {name: (self._get_fake_flavor(name), 1)
                        for name in ('compute', 'control')}

    def _get_fake_node(self, profile=None, possible_profiles=[],
                       provision_state='available'):
        caps = {'%s_profile' % p: '1'
                for p in possible_profiles}
        if profile is not None:
            caps['profile'] = profile
        caps = nodeutils.dict_to_capabilities(caps)
        return {
            'uuid': str(uuid4()),
            'properties': {'capabilities': caps},
            'provision_state': provision_state,
        }

    def _get_fake_flavor(self, name, profile=''):
        the_profile = profile or name
        return {
            'name': name,
            'profile': the_profile,
            'capabilities:boot_option': 'local',
            'capabilities:profile': the_profile
        }

    def _test(self, expected_result):
        action = validations.VerifyProfilesAction(self.nodes, self.flavors)
        result = action.run()

        self.assertEqual(expected_result, result)

    def test_no_matching_without_scale(self):
        self.flavors = {name: (object(), 0)
                        for name in self.flavors}
        self.nodes[:] = [self._get_fake_node(profile='fake'),
                         self._get_fake_node(profile='fake')]

        expected = mistral_workflow_utils.Result(
            data={
                'errors': [],
                'warnings': [],
            })
        self._test(expected)

    def test_exact_match(self):
        self.nodes[:] = [self._get_fake_node(profile='compute'),
                         self._get_fake_node(profile='control')]

        expected = mistral_workflow_utils.Result(
            data={
                'errors': [],
                'warnings': [],
            })
        self._test(expected)

    def test_nodes_with_no_profiles_present(self):
        self.nodes[:] = [self._get_fake_node(profile='compute'),
                         self._get_fake_node(profile=None),
                         self._get_fake_node(profile='foobar'),
                         self._get_fake_node(profile='control')]

        expected = mistral_workflow_utils.Result(
            data={
                'warnings': [
                    'There are 1 ironic nodes with no profile that will not '
                    'be used: %s' % self.nodes[1].get('uuid')
                ],
                'errors': [],
            })
        self._test(expected)

    def test_more_nodes_with_profiles_present(self):
        self.nodes[:] = [self._get_fake_node(profile='compute'),
                         self._get_fake_node(profile='compute'),
                         self._get_fake_node(profile='compute'),
                         self._get_fake_node(profile='control')]

        expected = mistral_workflow_utils.Result(
            data={
                'warnings': ["2 nodes with profile compute won't be used for "
                             "deployment now"],
                'errors': [],
            })
        self._test(expected)

    def test_no_nodes(self):
        # One error per each flavor
        expected = mistral_workflow_utils.Result(
            error={'errors': ['Error: only 0 of 1 requested ironic nodes are '
                              'tagged to profile compute (for flavor '
                              'compute)\n'
                              'Recommendation: tag more nodes using openstack '
                              'baremetal node set --property  '
                              '"capabilities=profile:compute,'
                              'boot_option:local" <NODE ID>',
                              'Error: only 0 of 1 requested ironic nodes are '
                              'tagged to profile control (for flavor '
                              'control).\n'
                              'Recommendation: tag more nodes using openstack '
                              'baremetal node set --property '
                              '"capabilities=profile:control,'
                              'boot_option:local" <NODE ID>'],
                   'warnings': []})

        action = validations.VerifyProfilesAction(self.nodes, self.flavors)
        result = action.run()
        self.assertEqual(expected.error['errors'].sort(),
                         result.error['errors'].sort())
        self.assertEqual(expected.error['warnings'], result.error['warnings'])
        self.assertEqual(None, result.data)

    def test_not_enough_nodes(self):
        self.nodes[:] = [self._get_fake_node(profile='compute')]
        expected = mistral_workflow_utils.Result(
            error={'errors': ['Error: only 0 of 1 requested ironic nodes are '
                              'tagged to profile control (for flavor '
                              'control).\n'
                              'Recommendation: tag more nodes using openstack '
                              'baremetal node set --property '
                              '"capabilities=profile:control,'
                              'boot_option:local" <NODE ID>'],
                   'warnings': []})
        self._test(expected)

    def test_scale(self):
        # active nodes with assigned profiles are fine
        self.nodes[:] = [self._get_fake_node(profile='compute',
                                             provision_state='active'),
                         self._get_fake_node(profile='control')]

        expected = mistral_workflow_utils.Result(
            data={
                'errors': [],
                'warnings': [],
            }
        )
        self._test(expected)

    def test_assign_profiles_wrong_state(self):
        # active nodes are not considered for assigning profiles
        self.nodes[:] = [self._get_fake_node(possible_profiles=['compute'],
                                             provision_state='active'),
                         self._get_fake_node(possible_profiles=['control'],
                                             provision_state='cleaning'),
                         self._get_fake_node(profile='compute',
                                             provision_state='error')]
        expected = mistral_workflow_utils.Result(
            error={
                'warnings': [
                    'There are 1 ironic nodes with no profile that will not '
                    'be used: %s' % self.nodes[0].get('uuid')
                ],
                'errors': [
                    'Error: only 0 of 1 requested ironic nodes are tagged to '
                    'profile control (for flavor control).\n'
                    'Recommendation: tag more nodes using openstack baremetal '
                    'node set --property "capabilities=profile:control,'
                    'boot_option:local" <NODE ID>',
                    'Error: only 0 of 1 requested ironic nodes are tagged to '
                    'profile compute (for flavor compute).\n'
                    'Recommendation: tag more nodes using openstack baremetal '
                    'node set --property "capabilities=profile:compute,'
                    'boot_option:local" <NODE ID>'
                ]
            })

        action = validations.VerifyProfilesAction(self.nodes, self.flavors)
        result = action.run()
        self.assertEqual(expected.error['errors'].sort(),
                         result.error['errors'].sort())
        self.assertEqual(expected.error['warnings'], result.error['warnings'])
        self.assertEqual(None, result.data)

    def test_no_spurious_warnings(self):
        self.nodes[:] = [self._get_fake_node(profile=None)]
        self.flavors = {'baremetal': (
            self._get_fake_flavor('baremetal', None), 1)}
        expected = mistral_workflow_utils.Result(
            error={
                'warnings': [
                    'There are 1 ironic nodes with no profile that will not '
                    'be used: %s' % self.nodes[0].get('uuid')
                ],
                'errors': [
                    'Error: only 0 of 1 requested ironic nodes are tagged to '
                    'profile baremetal (for flavor baremetal).\n'
                    'Recommendation: tag more nodes using openstack baremetal '
                    'node set --property "capabilities=profile:baremetal,'
                    'boot_option:local" <NODE ID>'
                ]
            })
        self._test(expected)
