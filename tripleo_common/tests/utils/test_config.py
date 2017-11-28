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

import fixtures
import mock
import os

from mock import call
from mock import patch

from tripleo_common.tests import base
from tripleo_common.tests.fake_config import fakes
from tripleo_common.utils import config as ooo_config


class TestConfig(base.TestCase):

    def setUp(self):
        super(TestConfig, self).setUp()

    @patch.object(ooo_config.Config, '_mkdir')
    @patch.object(ooo_config.Config, '_open_file')
    @mock.patch('tempfile.mkdtemp', autospec=True)
    def test_overcloud_config_generate_config(self,
                                              mock_tmpdir,
                                              mock_open,
                                              mock_mkdir):
        config_type_list = ['config_settings', 'global_config_settings',
                            'logging_sources', 'monitoring_subscriptions',
                            'service_config_settings',
                            'service_metadata_settings',
                            'service_names',
                            'upgrade_batch_tasks', 'upgrade_tasks']
        fake_role = [role for role in
                     fakes.FAKE_STACK['outputs'][1]['output_value']]

        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        mock_tmpdir.return_value = "/tmp/tht"
        self.config.download_config('overcloud', '/tmp', config_type_list)

        expected_mkdir_calls = [call('/tmp/tht/%s' % r) for r in fake_role]
        mock_mkdir.assert_has_calls(expected_mkdir_calls, any_order=True)
        expected_calls = []
        for config in config_type_list:
            for role in fake_role:
                if config == 'step_config':
                    expected_calls += [call('/tmp/tht/%s/%s.pp' %
                                            (role, config))]
                else:
                    expected_calls += [call('/tmp/tht/%s/%s.yaml' %
                                            (role, config))]
        mock_open.assert_has_calls(expected_calls, any_order=True)

    @patch.object(ooo_config.Config, '_mkdir')
    @patch.object(ooo_config.Config, '_open_file')
    @mock.patch('tempfile.mkdtemp', autospec=True)
    def test_overcloud_config_one_config_type(self,
                                              mock_tmpdir,
                                              mock_open,
                                              mock_mkdir):

        expected_config_type = 'config_settings'
        fake_role = [role for role in
                     fakes.FAKE_STACK['outputs'][1]['output_value']]

        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        mock_tmpdir.return_value = "/tmp/tht"
        self.config.download_config('overcloud', '/tmp', ['config_settings'])
        expected_mkdir_calls = [call('/tmp/tht/%s' % r) for r in fake_role]
        expected_calls = [call('/tmp/tht/%s/%s.yaml'
                          % (r, expected_config_type))
                          for r in fake_role]
        mock_mkdir.assert_has_calls(expected_mkdir_calls, any_order=True)
        mock_open.assert_has_calls(expected_calls, any_order=True)

    @mock.patch('os.mkdir')
    @mock.patch('six.moves.builtins.open')
    @mock.patch('tempfile.mkdtemp', autospec=True)
    def test_overcloud_config_wrong_config_type(self, mock_tmpdir,
                                                mock_open, mock_mkdir):
        args = {'name': 'overcloud', 'config_dir': '/tmp',
                'config_type': ['bad_config']}
        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        mock_tmpdir.return_value = "/tmp/tht"
        self.assertRaises(
            KeyError,
            self.config.download_config, *args)

    @mock.patch('tripleo_common.utils.config.Config.get_role_data',
                autospec=True)
    def test_overcloud_config_upgrade_tasks(self, mock_get_role_data):

        heat = mock.MagicMock()
        heat.stacks.get.return_value = fakes.create_tht_stack()
        self.config = ooo_config.Config(heat)
        self.tmp_dir = self.useFixture(fixtures.TempDir()).path
        fake_role = [role for role in
                     fakes.FAKE_STACK['outputs'][1]['output_value']]
        expected_tasks = {'FakeController': [{'name': 'Stop fake service',
                                              'service': 'name=fake '
                                              'state=stopped',
                                              'tags': 'step1',
                                              'when': 'step|int == 1'}],
                          'FakeCompute': [{'name': 'Stop fake service',
                                           'service':
                                           'name=fake state=stopped',
                                           'tags': 'step1',
                                           'when': ['step|int == 1',
                                                    'existingcondition']},
                                          {'name': 'Stop nova-'
                                           'compute service',
                                           'service':
                                           'name=openstack-nova-'
                                           'compute state=stopped',
                                           'tags': 'step1',
                                           'when': ['step|int == 1',
                                                    'existing', 'list']}]}
        mock_get_role_data.return_value = fake_role

        for role in fake_role:
            filedir = os.path.join(self.tmp_dir, role)
            os.makedirs(filedir)
            filepath = os.path.join(filedir, "upgrade_tasks_playbook.yaml")
            playbook_tasks = self.config._write_playbook_get_tasks(
                fakes.FAKE_STACK['outputs'][1]['output_value'][role]
                ['upgrade_tasks'], role, filepath)
            self.assertTrue(os.path.isfile(filepath))
            self.assertEqual(expected_tasks[role], playbook_tasks)
