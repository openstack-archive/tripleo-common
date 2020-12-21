#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

import datetime
import fixtures
import os
from unittest import mock
from unittest.mock import patch
from unittest.mock import call
import uuid
import warnings

import yaml


from tripleo_common import constants
from tripleo_common.tests import base
from tripleo_common.tests.fake_config import fakes
from tripleo_common.utils import config as ooo_config
from tripleo_common.utils.safe_import import git

RESOURCES_YAML_CONTENTS = """heat_template_version: 2016-04-08
resources:
  Controller:
    type: OS::Heat::ResourceGroup
  NotRoleContoller:
    type: OS::Dummy::DummyGroup
"""


class TestConfig(base.TestCase):

    def setUp(self):
        super(TestConfig, self).setUp()

    @patch.object(ooo_config.Config, 'initialize_git_repo')
    @patch.object(ooo_config.shutil, 'copyfile')
    @patch.object(ooo_config.Config, '_mkdir')
    @patch.object(ooo_config.Config, '_open_file')
    @patch.object(ooo_config.shutil, 'rmtree')
    def test_overcloud_config_generate_config(self,
                                              mock_rmtree,
                                              mock_open,
                                              mock_mkdir,
                                              mock_copyfile,
                                              mock_git_init):
        config_type_list = ['config_settings', 'global_config_settings',
                            'logging_sources', 'monitoring_subscriptions',
                            'service_config_settings',
                            'service_metadata_settings',
                            'service_names',
                            'upgrade_batch_tasks', 'upgrade_tasks',
                            'external_deploy_steps_tasks']

        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.config.fetch_config('overcloud')
        fake_role = list(self.config.stack_outputs.get('RoleData'))
        self.config.download_config('overcloud', '/tmp/tht', config_type_list)

        mock_git_init.assert_called_once_with('/tmp/tht')
        expected_mkdir_calls = [call('/tmp/tht/%s' % r) for r in fake_role]
        mock_mkdir.assert_has_calls(expected_mkdir_calls, any_order=True)
        mock_mkdir.assert_called()
        expected_calls = []
        for config in config_type_list:
            if 'external' in config:
                for step in range(constants.DEFAULT_STEPS_MAX):
                    expected_calls += [call('/tmp/tht/%s_step%s.yaml' %
                                       (config, step))]

            for role in fake_role:
                if 'external' in config:
                    continue
                elif config == 'step_config':
                    expected_calls += [call('/tmp/tht/%s/%s.pp' %
                                            (role, config))]
                elif config == 'param_config':
                    expected_calls += [call('/tmp/tht/%s/%s.json' %
                                            (role, config))]
                else:
                    expected_calls += [call('/tmp/tht/%s/%s.yaml' %
                                            (role, config))]
        mock_open.assert_has_calls(expected_calls, any_order=True)

    @patch.object(ooo_config.Config, 'initialize_git_repo')
    @patch.object(ooo_config.shutil, 'copyfile')
    @patch.object(ooo_config.Config, '_mkdir')
    @patch.object(ooo_config.Config, '_open_file')
    @patch.object(ooo_config.shutil, 'rmtree')
    def test_overcloud_config_one_config_type(self,
                                              mock_rmtree,
                                              mock_open,
                                              mock_mkdir,
                                              mock_copyfile,
                                              mock_git_init):

        expected_config_type = 'config_settings'

        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.config.fetch_config('overcloud')
        fake_role = list(self.config.stack_outputs.get('RoleData'))
        self.config.download_config('overcloud', '/tmp/tht',
                                    ['config_settings'])
        expected_mkdir_calls = [call('/tmp/tht/%s' % r) for r in fake_role]
        expected_calls = [call('/tmp/tht/%s/%s.yaml'
                          % (r, expected_config_type))
                          for r in fake_role]
        mock_mkdir.assert_has_calls(expected_mkdir_calls, any_order=True)
        mock_mkdir.assert_called()
        mock_open.assert_has_calls(expected_calls, any_order=True)
        mock_git_init.assert_called_once_with('/tmp/tht')

    @patch.object(ooo_config.git, 'Repo')
    @mock.patch('os.mkdir')
    @mock.patch('six.moves.builtins.open')
    @patch.object(ooo_config.shutil, 'rmtree')
    def test_overcloud_config_wrong_config_type(self, mock_rmtree,
                                                mock_open, mock_mkdir,
                                                mock_repo):
        args = {'name': 'overcloud', 'config_dir': '/tmp/tht',
                'config_type': ['bad_config']}
        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.assertRaises(
            KeyError,
            self.config.download_config, *args)

    def test_overcloud_config_upgrade_tasks(self):

        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.config.fetch_config('overcloud')
        self.tmp_dir = self.useFixture(fixtures.TempDir()).path
        fake_role = list(self.config.stack_outputs.get('RoleData'))
        expected_tasks = {'FakeController': {0: [],
                                             1: [{'name': 'Stop fake service',
                                                  'service': 'name=fake '
                                                  'state=stopped',
                                                  'when': 'step|int == 1'}],
                                             2: [],
                                             3: [],
                                             4: [],
                                             5: []},
                          'FakeCompute': {0: [],
                                          1: [{'name': 'Stop fake service',
                                               'service': 'name=fake '
                                               'state=stopped',
                                               'when': ['nova_api_enabled.rc'
                                                        ' == 0', False,
                                                        'httpd_enabled.rc'
                                                        ' != 0',
                                                        'step|int == 1']}],
                                          2: [{'name': 'Stop nova-compute '
                                               'service',
                                               'service': 'name=openstack-'
                                               'nova-compute state=stopped',
                                               'when': ['nova_compute_'
                                                        'enabled.rc == 0',
                                                        'step|int == 2',
                                                        'existing',
                                                        'list']}],
                                          3: [],
                                          4: [],
                                          5: []}}
        for role in fake_role:
            filedir = os.path.join(self.tmp_dir, role)
            os.makedirs(filedir)
            for step in range(constants.DEFAULT_STEPS_MAX):
                filepath = os.path.join(filedir, "upgrade_tasks_step%s.yaml"
                                        % step)
                playbook_tasks = self.config._write_tasks_per_step(
                    self.config.stack_outputs.get('RoleData')[role]
                    ['upgrade_tasks'], filepath, step)
                self.assertTrue(os.path.isfile(filepath))
                self.assertEqual(expected_tasks[role][step], playbook_tasks)

    def test_get_server_names(self):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)
        self.config.stack_outputs = {
            'RoleNetHostnameMap': {
                'Controller': {
                    'ctlplane': [
                        'c0.ctlplane.localdomain',
                        'c1.ctlplane.localdomain',
                        'c2.ctlplane.localdomain']}},
            'ServerIdData': {
                'server_ids': {
                    'Controller': [
                        '8269f736',
                        '2af0a373',
                        'c8479674']}}}
        server_names = self.config.get_server_names()
        expected = {'2af0a373': 'c1', '8269f736': 'c0', 'c8479674': 'c2'}
        self.assertEqual(expected, server_names)

    def test_get_role_config(self):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)
        self.config.stack_outputs = {'RoleConfig': None}
        role_config = self.config.get_role_config()
        self.assertEqual({}, role_config)

    def test_get_deployment_data(self):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)
        stack = 'overcloud'
        first = mock.MagicMock()
        first.creation_time = datetime.datetime.now() - datetime.timedelta(2)
        second = mock.MagicMock()
        second.creation_time = datetime.datetime.now() - datetime.timedelta(1)
        third = mock.MagicMock()
        third.creation_time = datetime.datetime.now()
        # Set return_value in a nonsorted order, as we expect the function to
        # sort, so that's what we want to test
        heat.resources.list.return_value = [second, third, first]

        deployment_data = self.config.get_deployment_data(stack)
        self.assertTrue(heat.resources.list.called)
        self.assertEqual(
            heat.resources.list.call_args,
            mock.call(stack,
                      filters=dict(name=constants.TRIPLEO_DEPLOYMENT_RESOURCE),
                      nested_depth=constants.NESTED_DEPTH,
                      with_detail=True))
        self.assertEqual(deployment_data,
                         [first, second, third])

    def _get_config_data(self, datafile):
        config_data_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            'data',
            datafile)
        with open(config_data_path) as fin:
            config_data = yaml.safe_load(fin.read())
        deployment_data = []

        for deployment in config_data['deployments']:
            deployment_mock = mock.MagicMock()
            deployment_mock.id = deployment['deployment']
            deployment_mock.attributes = dict(
                value=dict(server=deployment['server'],
                           deployment=deployment['deployment'],
                           config=deployment['config'],
                           name=deployment['name']))
            deployment_data.append(deployment_mock)

        configs = config_data['configs']

        return deployment_data, configs

    def _get_deployment_id(self, deployment):
        return deployment.attributes['value']['deployment']

    def _get_config_dict(self, deployment_id):
        deployment = list(filter(
            lambda d: d.id == deployment_id, self.deployments))[0]
        config = self.configs[deployment.attributes['value']['config']].copy()
        config['inputs'] = []
        config['inputs'].append(dict(
            name='deploy_server_id',
            value=deployment.attributes['value']['server']))
        return config

    def _get_yaml_file(self, file_name):
        file_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            'data',
            file_name)
        with open(file_path) as fin:
            return yaml.safe_load(fin.read())

    @patch.object(ooo_config.Config, 'initialize_git_repo')
    @patch('tripleo_common.utils.config.Config.get_deployment_resource_id')
    @patch('tripleo_common.utils.config.Config.get_config_dict')
    @patch('tripleo_common.utils.config.Config.get_deployment_data')
    def test_config_download(self, mock_deployment_data, mock_config_dict,
                             mock_deployment_resource_id,
                             mock_git_init):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)
        stack = mock.MagicMock()
        heat.stacks.get.return_value = stack
        stack.outputs = [
            {'output_key': 'RoleNetHostnameMap',
             'output_value': {
                 'Controller': {
                     'ctlplane': [
                         'overcloud-controller-0.ctlplane.localdomain']},
                 'Compute': {
                     'ctlplane': [
                         'overcloud-novacompute-0.ctlplane.localdomain',
                         'overcloud-novacompute-1.ctlplane.localdomain',
                         'overcloud-novacompute-2.ctlplane.localdomain']}}},
            {'output_key': 'ServerIdData',
             'output_value': {
                 'server_ids': {
                     'Controller': [
                         '00b3a5e1-5e8e-4b55-878b-2fa2271f15ad'],
                     'Compute': [
                         'a7db3010-a51f-4ae0-a791-2364d629d20d',
                         '8b07cd31-3083-4b88-a433-955f72039e2c',
                         '169b46f8-1965-4d90-a7de-f36fb4a830fe']}}},
            {'output_key': 'HostnameNetworkConfigMap',
             'output_value': {}},
            {'output_key': 'AnsibleHostVarsMap',
             'output_value': {
                 'Controller': {
                     'overcloud-controller-0': {
                         'uuid': 0,
                         'my_var': 'foo'}},
                 'Compute': {
                     'overcloud-novacompute-0': {
                         'uuid': 1},
                     'overcloud-novacompute-1': {
                         'uuid': 2},
                     'overcloud-novacompute-2': {
                         'uuid': 3}}}},
            {'output_key': 'RoleData',
             'output_value': {
                 'Controller': {
                     'ansible_group_vars': {
                         'chrony_host': 'localhost',
                         'chrony_acl': 'none',
                     }}}},
            {'output_key': 'RoleGroupVars',
             'output_value': {
                 'Controller': {
                     'any_errors_fatal': True,
                     'chrony_host': '192.168.2.1',
                     'chrony_foo': 'bar',
                     'max_fail_percentage': 15},
                 'Compute': {
                     'any_errors_fatal': True,
                     'max_fail_percentage': 15},
                 }}]
        deployment_data, configs = \
            self._get_config_data('config_data.yaml')
        self.configs = configs
        self.deployments = deployment_data
        mock_deployment_data.return_value = deployment_data
        mock_deployment_resource_id.side_effect = self._get_deployment_id
        mock_config_dict.side_effect = self._get_config_dict

        self.tmp_dir = self.useFixture(fixtures.TempDir()).path
        tmp_path = self.config.download_config(stack, self.tmp_dir)

        mock_git_init.assert_called_once_with(self.tmp_dir)
        for f in ['Controller',
                  'Compute', ]:

            with open(os.path.join(tmp_path, 'group_vars', f)) as fin:
                self.assertEqual(
                    self._get_yaml_file(f),
                    yaml.safe_load(fin.read()))

        for f in ['overcloud-controller-0',
                  'overcloud-novacompute-0',
                  'overcloud-novacompute-1',
                  'overcloud-novacompute-2']:
            with open(os.path.join(tmp_path, 'host_vars', f)) as fin:
                self.assertEqual(
                    self._get_yaml_file(os.path.join('host_vars', f)),
                    yaml.safe_load(fin.read()))

        for d in ['ControllerHostEntryDeployment',
                  'NetworkDeployment',
                  'MyExtraConfigPost',
                  'MyPostConfig']:
            with open(os.path.join(tmp_path, 'Controller',
                                   'overcloud-controller-0',
                                   d)) as fin:
                self.assertEqual(
                    yaml.safe_load(fin.read()),
                    self._get_yaml_file(os.path.join(
                                        'overcloud-controller-0',
                                        d)))

        for d in ['ComputeHostEntryDeployment',
                  'NetworkDeployment',
                  'MyExtraConfigPost']:

            with open(os.path.join(tmp_path, 'Compute',
                                   'overcloud-novacompute-0',
                                   d)) as fin:
                self.assertEqual(
                    yaml.safe_load(fin.read()),
                    self._get_yaml_file(os.path.join(
                                        'overcloud-novacompute-0',
                                        d)))

        for d in ['ComputeHostEntryDeployment',
                  'NetworkDeployment',
                  'MyExtraConfigPost']:
            with open(os.path.join(tmp_path, 'Compute',
                                   'overcloud-novacompute-1',
                                   d)) as fin:
                self.assertEqual(
                    yaml.safe_load(fin.read()),
                    self._get_yaml_file(os.path.join(
                                        'overcloud-novacompute-1',
                                        d)))

        for d in ['ComputeHostEntryDeployment',
                  'NetworkDeployment',
                  'MyExtraConfigPost',
                  'AnsibleDeployment']:
            with open(os.path.join(tmp_path, 'Compute',
                                   'overcloud-novacompute-2',
                                   d)) as fin:
                self.assertEqual(
                    yaml.safe_load(fin.read()),
                    self._get_yaml_file(os.path.join(
                                        'overcloud-novacompute-2',
                                        d)))

    @patch.object(ooo_config.Config, 'initialize_git_repo')
    @patch('tripleo_common.utils.config.Config.get_deployment_resource_id')
    @patch('tripleo_common.utils.config.Config.get_config_dict')
    @patch('tripleo_common.utils.config.Config.get_deployment_data')
    def test_config_download_os_apply_config(
        self, mock_deployment_data, mock_config_dict,
        mock_deployment_resource_id, mock_git_init):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)
        stack = mock.MagicMock()
        heat.stacks.get.return_value = stack
        heat.resources.get.return_value = mock.MagicMock()
        stack.outputs = [
            {'output_key': 'RoleNetHostnameMap',
             'output_value': {
                 'Controller': {
                     'ctlplane': [
                         'overcloud-controller-0.ctlplane.localdomain']},
                 'Compute': {
                     'ctlplane': [
                         'overcloud-novacompute-0.ctlplane.localdomain',
                         'overcloud-novacompute-1.ctlplane.localdomain',
                         'overcloud-novacompute-2.ctlplane.localdomain']}}},
            {'output_key': 'ServerIdData',
             'output_value': {
                 'server_ids': {
                     'Controller': [
                         '00b3a5e1-5e8e-4b55-878b-2fa2271f15ad'],
                     'Compute': [
                         'a7db3010-a51f-4ae0-a791-2364d629d20d',
                         '8b07cd31-3083-4b88-a433-955f72039e2c',
                         '169b46f8-1965-4d90-a7de-f36fb4a830fe']}}},
            {'output_key': 'HostnameNetworkConfigMap',
             'output_value': {}},
            {'output_key': 'RoleGroupVars',
             'output_value': {
                 'Controller': {
                     'any_errors_fatal': 'yes',
                     'max_fail_percentage': 15},
                 'Compute': {
                     'any_errors_fatal': 'yes',
                     'max_fail_percentage': 15},
             }}]
        deployment_data, configs = \
            self._get_config_data('config_data.yaml')

        # Add a group:os-apply-config config and deployment
        config_uuid = str(uuid.uuid4())
        configs[config_uuid] = dict(
            id=config_uuid,
            config=dict(a='a'),
            group='os-apply-config',
            outputs=[])

        deployment_uuid = str(uuid.uuid4())
        deployment_mock = mock.MagicMock()
        deployment_mock.id = deployment_uuid
        deployment_mock.attributes = dict(
            value=dict(server='00b3a5e1-5e8e-4b55-878b-2fa2271f15ad',
                       deployment=deployment_uuid,
                       config=config_uuid,
                       name='OsApplyConfigDeployment'))
        deployment_data.append(deployment_mock)

        self.configs = configs
        self.deployments = deployment_data
        mock_deployment_data.return_value = deployment_data
        mock_config_dict.side_effect = self._get_config_dict
        mock_deployment_resource_id.side_effect = self._get_deployment_id

        self.tmp_dir = self.useFixture(fixtures.TempDir()).path
        with warnings.catch_warnings(record=True) as w:
            self.config.download_config(stack, self.tmp_dir)
            mock_git_init.assert_called_once_with(self.tmp_dir)
            # check that we got at least one of the warnings that we expected
            # to throw
            self.assertGreaterEqual(len(w), 1)
            self.assertGreaterEqual(len([x for x in w
                                         if issubclass(x.category,
                                                       DeprecationWarning)]),
                                    1)
            self.assertGreaterEqual(len([x for x in w
                                         if "group:os-apply-config"
                                         in str(x.message)]),
                                    1)

    @patch.object(ooo_config.Config, 'initialize_git_repo')
    @patch('tripleo_common.utils.config.Config.get_deployment_resource_id')
    @patch('tripleo_common.utils.config.Config.get_deployment_data')
    def test_config_download_no_deployment_name(
        self, mock_deployment_data, mock_deployment_resource_id,
        mock_git_init):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)
        stack = mock.MagicMock()
        heat.stacks.get.return_value = stack
        heat.resources.get.return_value = mock.MagicMock()

        deployment_data, _ = self._get_config_data('config_data.yaml')

        # Delete the name of the first deployment and his parent.
        del deployment_data[0].attributes['value']['name']
        deployment_data[0].parent_resource = None
        self.deployments = deployment_data

        mock_deployment_data.return_value = deployment_data
        mock_deployment_resource_id.side_effect = self._get_deployment_id

        self.tmp_dir = self.useFixture(fixtures.TempDir()).path
        self.assertRaises(ValueError,
                          self.config.download_config, stack, self.tmp_dir)
        mock_git_init.assert_called_once_with(self.tmp_dir)

    @patch.object(ooo_config.Config, 'initialize_git_repo')
    @patch('tripleo_common.utils.config.Config.get_deployment_resource_id')
    @patch('tripleo_common.utils.config.Config.get_deployment_data')
    def test_config_download_warn_grandparent_resource_name(
        self, mock_deployment_data, mock_deployment_resource_id,
        mock_git_init):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)
        stack = mock.MagicMock()
        heat.stacks.get.return_value = stack
        heat.resources.get.return_value = mock.MagicMock()

        deployment_data, _ = self._get_config_data('config_data.yaml')

        # Set the name of the deployment to an integer to trigger looking up
        # the grandparent resource name
        deployment_data[0].attributes['value']['name'] = 1
        self.deployments = deployment_data

        mock_deployment_data.return_value = deployment_data
        mock_deployment_resource_id.side_effect = self._get_deployment_id

        self.tmp_dir = self.useFixture(fixtures.TempDir()).path
        with warnings.catch_warnings(record=True) as w:
            self.assertRaises(ValueError,
                              self.config.download_config, stack, self.tmp_dir)
            self.assertGreaterEqual(len(w), 1)
            self.assertGreaterEqual(len([x for x in w
                                         if "grandparent"
                                         in str(x.message)]),
                                    1)

        mock_git_init.assert_called_once_with(self.tmp_dir)

    @patch.object(ooo_config.Config, 'initialize_git_repo')
    @patch('tripleo_common.utils.config.Config.get_deployment_resource_id')
    @patch('tripleo_common.utils.config.Config.get_config_dict')
    @patch('tripleo_common.utils.config.Config.get_deployment_data')
    def test_config_download_no_deployment_uuid(self, mock_deployment_data,
                                                mock_config_dict,
                                                mock_deployment_resource_id,
                                                mock_git_init):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)
        stack = mock.MagicMock()
        heat.stacks.get.return_value = stack
        heat.resources.get.return_value = mock.MagicMock()

        stack.outputs = [
            {'output_key': 'RoleNetHostnameMap',
             'output_value': {
                 'Controller': {
                     'ctlplane': [
                         'overcloud-controller-0.ctlplane.localdomain']},
                 'Compute': {
                     'ctlplane': [
                         'overcloud-novacompute-0.ctlplane.localdomain',
                         'overcloud-novacompute-1.ctlplane.localdomain',
                         'overcloud-novacompute-2.ctlplane.localdomain']}}},
            {'output_key': 'ServerIdData',
             'output_value': {
                 'server_ids': {
                     'Controller': [
                         '00b3a5e1-5e8e-4b55-878b-2fa2271f15ad'],
                     'Compute': [
                         'a7db3010-a51f-4ae0-a791-2364d629d20d',
                         '8b07cd31-3083-4b88-a433-955f72039e2c',
                         '169b46f8-1965-4d90-a7de-f36fb4a830fe']}}},
            {'output_key': 'HostnameNetworkConfigMap',
             'output_value': {}},
            {'output_key': 'RoleGroupVars',
             'output_value': {
                 'Controller': {
                     'any_errors_fatal': 'yes',
                     'max_fail_percentage': 15},
                 'Compute': {
                     'any_errors_fatal': 'yes',
                     'max_fail_percentage': 15},
             }}]
        deployment_data, configs = self._get_config_data('config_data.yaml')

        # Set the deployment to TripleOSoftwareDeployment for the first
        # deployment
        deployment_data[0].attributes['value']['deployment'] = \
            'TripleOSoftwareDeployment'

        # Set the physical_resource_id as '' for the second deployment
        deployment_data[1].attributes['value']['deployment'] = ''

        self.configs = configs
        self.deployments = deployment_data
        mock_deployment_data.return_value = deployment_data
        mock_config_dict.side_effect = self._get_config_dict
        mock_deployment_resource_id.side_effect = self._get_deployment_id

        self.tmp_dir = self.useFixture(fixtures.TempDir()).path
        with warnings.catch_warnings(record=True) as w:
            self.config.download_config(stack, self.tmp_dir)
            assert "Skipping deployment" in str(w[-1].message)
            assert "Skipping deployment" in str(w[-2].message)

    @patch.object(ooo_config.Config, 'initialize_git_repo')
    @patch.object(ooo_config.git, 'Repo')
    @patch.object(ooo_config.shutil, 'copyfile')
    @patch.object(ooo_config.Config, '_mkdir')
    @patch.object(ooo_config.Config, '_open_file')
    @patch.object(ooo_config.shutil, 'rmtree')
    @patch.object(ooo_config.os.path, 'exists')
    def test_overcloud_config_dont_preserve_config(self,
                                                   mock_os_path_exists,
                                                   mock_rmtree,
                                                   mock_open,
                                                   mock_mkdir,
                                                   mock_copyfile,
                                                   mock_repo,
                                                   mock_git_init):
        config_type_list = ['config_settings', 'global_config_settings',
                            'logging_sources', 'monitoring_subscriptions',
                            'service_config_settings',
                            'service_metadata_settings',
                            'service_names',
                            'upgrade_batch_tasks', 'upgrade_tasks',
                            'external_deploy_tasks']

        mock_os_path_exists.get.return_value = True
        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.config.fetch_config('overcloud')
        fake_role = list(self.config.stack_outputs.get('RoleData'))
        self.config.download_config('overcloud', '/tmp/tht', config_type_list,
                                    False)

        mock_git_init.assert_called_once_with('/tmp/tht')
        expected_rmtree_calls = [call('/tmp/tht')]
        mock_rmtree.assert_has_calls(expected_rmtree_calls)

        expected_mkdir_calls = [call('/tmp/tht/%s' % r) for r in fake_role]
        mock_mkdir.assert_has_calls(expected_mkdir_calls, any_order=True)
        mock_mkdir.assert_called()
        expected_calls = []
        for config in config_type_list:
            for role in fake_role:
                if 'external' in config:
                    continue
                elif config == 'step_config':
                    expected_calls += [call('/tmp/tht/%s/%s.pp' %
                                            (role, config))]
                elif config == 'param_config':
                    expected_calls += [call('/tmp/tht/%s/%s.json' %
                                            (role, config))]
                else:
                    expected_calls += [call('/tmp/tht/%s/%s.yaml' %
                                            (role, config))]
        mock_open.assert_has_calls(expected_calls, any_order=True)

    @patch.object(ooo_config.shutil, 'rmtree')
    @patch.object(ooo_config.os.path, 'exists')
    def test_create_config_dir(self, mock_os_path_exists, mock_rmtree):
        mock_os_path_exists.get.return_value = True
        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.config.create_config_dir('/tmp/tht', False)
        expected_rmtree_calls = [call('/tmp/tht')]
        mock_rmtree.assert_has_calls(expected_rmtree_calls)

    def test_initialize_git_repo(self):
        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.tmp_dir = self.useFixture(fixtures.TempDir()).path
        repo = self.config.initialize_git_repo(self.tmp_dir)
        self.assertIsInstance(repo, git.Repo)

    @patch('tripleo_common.utils.config.Config.get_config_dict')
    @patch('tripleo_common.utils.config.Config.get_deployment_data')
    def test_write_config(self, mock_deployment_data, mock_config_dict):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)
        stack = mock.MagicMock()
        heat.stacks.get.return_value = stack

        stack.outputs = [
            {'output_key': 'RoleNetHostnameMap',
             'output_value': {
                 'Controller': {
                     'ctlplane': [
                         'overcloud-controller-0.ctlplane.localdomain']},
                 'Compute': {
                     'ctlplane': [
                         'overcloud-novacompute-0.ctlplane.localdomain',
                         'overcloud-novacompute-1.ctlplane.localdomain',
                         'overcloud-novacompute-2.ctlplane.localdomain']}}},
            {'output_key': 'ServerIdData',
             'output_value': {
                 'server_ids': {
                     'Controller': [
                         '00b3a5e1-5e8e-4b55-878b-2fa2271f15ad'],
                     'Compute': [
                         'a7db3010-a51f-4ae0-a791-2364d629d20d',
                         '8b07cd31-3083-4b88-a433-955f72039e2c',
                         '169b46f8-1965-4d90-a7de-f36fb4a830fe']}}},
            {'output_key': 'RoleData',
             'output_value': {
                 'Controller': {
                     'ansible_group_vars': {
                         'chrony_host': 'localhost',
                         'chrony_acl': 'none',
                     }}}},
            {'output_key': 'RoleGroupVars',
             'output_value': {
                 'Controller': {
                     'any_errors_fatal': True,
                     'chrony_host': '192.168.2.1',
                     'chrony_foo': 'bar',
                     'max_fail_percentage': 15},
                 'Compute': {
                     'any_errors_fatal': True,
                     'max_fail_percentage': 15}}},
            {'output_key': 'HostnameNetworkConfigMap',
             'output_value': {}}
            ]
        deployment_data, configs = \
            self._get_config_data('config_data.yaml')
        self.configs = configs
        self.deployments = deployment_data

        stack_data = self.config.fetch_config('overcloud')
        mock_deployment_data.return_value = deployment_data
        mock_config_dict.side_effect = self._get_config_dict
        config_dir = self.useFixture(fixtures.TempDir()).path

        self.config.write_config(stack_data, 'overcloud', config_dir)

        for f in ['Controller',
                  'Compute', ]:
            with open(os.path.join(config_dir, 'group_vars', f)) as fin:
                self.assertEqual(
                    yaml.safe_load(fin.read()),
                    self._get_yaml_file(f))

        for d in ['ControllerHostEntryDeployment',
                  'NetworkDeployment',
                  'MyExtraConfigPost',
                  'MyPostConfig']:
            with open(os.path.join(config_dir, 'Controller',
                                   'overcloud-controller-0', d)) as fin:
                self.assertEqual(
                    yaml.safe_load(fin.read()),
                    self._get_yaml_file(os.path.join(
                        'overcloud-controller-0',
                        d)))

        for d in ['ComputeHostEntryDeployment',
                  'NetworkDeployment',
                  'MyExtraConfigPost']:
            with open(os.path.join(config_dir, 'Compute',
                                   'overcloud-novacompute-0',
                                   d)) as fin:
                self.assertEqual(
                    yaml.safe_load(fin.read()),
                    self._get_yaml_file(os.path.join(
                        'overcloud-novacompute-0',
                        d)))

        for d in ['ComputeHostEntryDeployment',
                  'NetworkDeployment',
                  'MyExtraConfigPost']:
            with open(os.path.join(config_dir, 'Compute',
                                   'overcloud-novacompute-1',
                                   d)) as fin:
                self.assertEqual(
                    yaml.safe_load(fin.read()),
                    self._get_yaml_file(os.path.join(
                        'overcloud-novacompute-1',
                        d)))

        for d in ['ComputeHostEntryDeployment',
                  'NetworkDeployment',
                  'MyExtraConfigPost',
                  'AnsibleDeployment']:
            with open(os.path.join(config_dir, 'Compute',
                                   'overcloud-novacompute-2', d)) as fin:
                self.assertEqual(
                    yaml.safe_load(fin.read()),
                    self._get_yaml_file(os.path.join(
                        'overcloud-novacompute-2',
                        d)))

    @patch('tripleo_common.utils.config.Config.get_config_dict')
    @patch('tripleo_common.utils.config.Config.get_deployment_data')
    @patch.object(ooo_config.yaml, 'safe_load')
    def test_validate_config(self, mock_yaml, mock_deployment_data,
                             mock_config_dict):
        stack_config = """
        Controller:
          ctlplane:
            overcloud-controller-0.ctlplane.localdomain
        Compute:
          ctlplane:
            overcloud-novacompute-0.ctlplane.localdomain
            overcloud-novacompute-1.ctlplane.localdomain
            overcloud-novacompute-2.ctlplane.localdomain
        """
        yaml_file = '/tmp/testfile.yaml'
        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.config.validate_config(stack_config, yaml_file)
        expected_yaml_safe_load_calls = [call(stack_config)]
        mock_yaml.assert_has_calls(expected_yaml_safe_load_calls)

    @patch('tripleo_common.utils.config.Config.get_config_dict')
    @patch('tripleo_common.utils.config.Config.get_deployment_data')
    def test_validate_config_invalid_yaml(self, mock_deployment_data,
                                          mock_config_dict):
        # Use invalid YAML to assert that we properly handle the exception
        stack_config = """
        Controller:
          ctlplane:
            overcloud-controller-0.ctlplane.localdomain
        Compute:
          ctlplane:
        overcloud-novacompute-0.ctlplane.localdomain
        overcloud-novacompute-1.ctlplane.localdomain
        overcloud-novacompute-2.ctlplane.localdomain
        """
        yaml_file = '/tmp/testfile.yaml'
        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.assertRaises(yaml.scanner.ScannerError,
                          self.config.validate_config, stack_config, yaml_file)

    @patch('tripleo_common.utils.config.Config.get_network_config_data')
    def test_render_network_config_empty_dict(self,
                                              mock_get_network_config_data):
        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        config_mock = mock.MagicMock()
        config_mock.config = {}
        heat.software_configs.get.return_value = config_mock

        self.config = ooo_config.Config(heat)
        stack = mock.Mock()
        server_roles = dict(Controller='controller')
        mock_get_network_config_data.return_value = dict(
            Controller='56f27b7a-7bb8-40bc-bfdb-a46f7f806b88')
        config_dir = '/tmp/tht'
        self.config.render_network_config(stack, config_dir, server_roles)

    @patch.object(ooo_config.Config, '_open_file')
    @patch('tripleo_common.utils.config.Config.get_network_config_data')
    def test_render_network_config(self,
                                   mock_get_network_config_data,
                                   mock_open):
        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        config_mock = mock.MagicMock()
        config_mock.config = 'some config'
        heat.software_configs.get.return_value = config_mock

        self.config = ooo_config.Config(heat)
        stack = mock.Mock()
        server_roles = dict(node1='Controller')
        mock_get_network_config_data.return_value = dict(
            node1='56f27b7a-7bb8-40bc-bfdb-a46f7f806b88',
            node2='56f27b7a-7bb8-40bc-bfdb-a46f7f806b88')
        config_dir = '/tmp/tht'
        self.config.render_network_config(stack, config_dir, server_roles)
        self.assertEqual(2, mock_open.call_count)
        self.assertEqual('/tmp/tht/Controller/node1/NetworkConfig',
                         mock_open.call_args_list[0][0][0])
        self.assertEqual('/tmp/tht/Controller/NetworkConfig',
                         mock_open.call_args_list[1][0][0])


class OvercloudConfigTest(base.TestCase):

    def setUp(self,):
        super(OvercloudConfigTest, self).setUp()
        self.plan = 'overcloud'
        self.delete_after = 3600
        self.config_container = 'config-overcloud'

        # setup swift
        self.template_files = (
            'some-name.yaml',
            'some-other-name.yaml',
            'yet-some-other-name.yaml',
            'finally-another-name.yaml'
        )
        self.swift = mock.MagicMock()
        self.swift.get_container.return_value = (
            {'x-container-meta-usage-tripleo': 'plan'}, [
                {
                    'name': tf,
                    'last_modified': '2018-11-05'
                } for tf in self.template_files
            ]
        )
        self.swift.get_object.return_value = ({}, RESOURCES_YAML_CONTENTS)

    @mock.patch('tripleo_common.utils.swift.delete_container')
    @mock.patch('tripleo_common.utils.swift.download_container')
    @mock.patch('tripleo_common.utils.config.Config.download_config')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_get_overcloud_config(self, mock_create_tarball,
                                  mock_config,
                                  mock_swift_download,
                                  mock_swift_delete):
        heat = mock.MagicMock()
        heat.stacks.get.return_value = mock.MagicMock(
            stack_name='stack', id='stack_id')
        mock_config.return_value = '/tmp/fake-path'

        ooo_config.get_overcloud_config(
            self.swift, heat,
            self.plan,
            self.config_container,
            '/tmp/fake-path')

        mock_swift_download.assert_called_once_with(self.swift,
                                                    self.config_container,
                                                    '/tmp/fake-path')
        mock_swift_delete.assert_called_once_with(self.swift,
                                                  self.config_container)
        self.assertEqual(2, self.swift.put_object.call_count)
        self.assertEqual(mock.call(
            'config-overcloud', 'config-overcloud.tar.gz',
            self.swift.put_object.call_args_list[1][0][2]),  # closed file call
            self.swift.put_object.call_args_list[1])
        mock_create_tarball.assert_called_once()
        self.assertEqual(dict(excludes=['.tox', '*.pyc', '*.pyo']),
                         mock_create_tarball.call_args[1])

    @mock.patch('tripleo_common.utils.config.os.unlink')
    @mock.patch('tripleo_common.utils.config.os.path.exists')
    @mock.patch('tripleo_common.utils.config.os.symlink')
    @mock.patch('tripleo_common.utils.swift.download_container')
    @mock.patch('tempfile.mkdtemp')
    def test_download_config(self, mock_mkdtemp,
                             mock_swiftutils,
                             mock_os_symlink,
                             mock_os_path_exists,
                             mock_os_unlink):
        mock_mkdtemp.return_value = '/tmp/tripleo-foo-config'
        ooo_config.download_overcloud_config(self.swift,
                                             self.config_container)
        mock_swiftutils.assert_called_once_with(self.swift,
                                                self.config_container,
                                                '/tmp/tripleo-foo-config')

    @mock.patch('tripleo_common.utils.config.os.path.exists')
    @mock.patch('tripleo_common.utils.config.os.symlink')
    @mock.patch('tripleo_common.utils.swift.download_container')
    @mock.patch('tempfile.mkdtemp')
    def test_download_create_latest_symlink(
            self, mock_mkdtemp,
            mock_swiftutils,
            mock_os_symlink,
            mock_os_path_exists):
        mock_mkdtemp.return_value = '/var/lib/mistral/uuid'
        mock_os_path_exists.return_value = False
        ooo_config.download_overcloud_config(self.swift,
                                             self.config_container)
        mock_swiftutils.assert_called_once_with(self.swift,
                                                self.config_container,
                                                mock_mkdtemp())
        mock_os_symlink.assert_called_once_with(
            '/var/lib/mistral/uuid',
            os.path.join(os.path.dirname('/var/lib/mistral/uuid'),
                         'config-download-latest'))

    @mock.patch('tripleo_common.utils.config.os.unlink')
    @mock.patch('tripleo_common.utils.config.os.path.exists')
    @mock.patch('tripleo_common.utils.config.os.symlink')
    @mock.patch('tripleo_common.utils.swift.download_container')
    @mock.patch('tempfile.mkdtemp')
    def test_download_update_latest_symlink(
            self, mock_mkdtemp,
            mock_swiftutils,
            mock_os_symlink,
            mock_os_path_exists,
            mock_os_unlink):
        mock_mkdtemp.return_value = '/var/lib/mistral/uuid'
        mock_os_path_exists.return_value = True
        ooo_config.download_overcloud_config(self.swift,
                                             self.config_container)
        mock_swiftutils.assert_called_once_with(self.swift,
                                                self.config_container,
                                                mock_mkdtemp())
        mock_os_symlink.assert_called_once_with(
            '/var/lib/mistral/uuid',
            os.path.join(os.path.dirname('/var/lib/mistral/uuid'),
                         'config-download-latest'))
        mock_os_unlink.assert_called_once_with(
            '/var/lib/mistral/config-download-latest')

    @patch.object(ooo_config.Config, '_open_file')
    def test_overcloud_config__write_tasks_per_step(self, mock_open_file):
        heat = mock.MagicMock()
        self.config = ooo_config.Config(heat)

        # TODO: how can I share this tasks definition between to test
        # as a fixture So that I do two several test cases instead of
        # a big one.
        tasks = [
            {
                "when": "step|int == 0",
                "name": "Simple check"
            },
            {
                "when": "(step|int == 0)",
                "name": "Check within parenthesis"
            },
            {
                "when": ["step|int == 0", "test1", False],
                "name": "Check with list with boolean"
            },
            {
                "when": ["test1", False, "step|int == 0"],
                "name": "Check with list with boolean other order"
            },
            {
                "when": "step|int == 0 or step|int == 3",
                "name": "Check with boolean expression"
            },
            {
                "when": "(step|int == 0 or step|int == 3) and other_cond",
                "name": "Complex boolean expression"
            },
            {
                "name": "Task with no conditional"
            }
        ]

        # Everything should come back
        tasks_per_step = self.config._write_tasks_per_step(
            tasks,
            'Compute/update_tasks_step0.yaml',
            0
        )

        self.assertEqual(tasks, tasks_per_step)

        # Using stict the tasks with no conditional will be dropped
        tasks_per_step = self.config._write_tasks_per_step(
            tasks,
            'Compute/update_tasks_step0.yaml',
            0,
            strict=True,
        )

        expected_tasks = [task for task in tasks
                          if task != {"name": "Task with no conditional"}]
        self.assertEqual(expected_tasks,
                         tasks_per_step)

        # Some tasks will be filtered out for step 3.
        tasks_per_step = self.config._write_tasks_per_step(
            tasks,
            'Compute/update_tasks_step3.yaml',
            3
        )

        self.assertEqual(
            [
                {
                    "when": "step|int == 0 or step|int == 3",
                    "name": "Check with boolean expression"
                },
                {
                    "when": "(step|int == 0 or step|int == 3) and other_cond",
                    "name": "Complex boolean expression"
                },
                {
                    "name": "Task with no conditional"
                }
            ],
            tasks_per_step)

        # Even more tasks will be filtered out for step 3 with strict.
        tasks_per_step = self.config._write_tasks_per_step(
            tasks,
            'Compute/update_tasks_step3.yaml',
            3,
            strict=True,
        )

        self.assertEqual(
            [
                {
                    "when": "step|int == 0 or step|int == 3",
                    "name": "Check with boolean expression"
                },
                {
                    "when": "(step|int == 0 or step|int == 3) and other_cond",
                    "name": "Complex boolean expression"
                },
            ],
            tasks_per_step)
