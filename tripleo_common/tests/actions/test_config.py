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
import mock

from tripleo_common.actions import config
from tripleo_common.tests import base

RESOURCES_YAML_CONTENTS = """heat_template_version: 2016-04-08
resources:
  Controller:
    type: OS::Heat::ResourceGroup
  NotRoleContoller:
    type: OS::Dummy::DummyGroup
"""


class GetOvercloudConfigActionTest(base.TestCase):

    def setUp(self,):
        super(GetOvercloudConfigActionTest, self).setUp()
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
                {'name': tf} for tf in self.template_files
            ]
        )
        self.swift.get_object.return_value = ({}, RESOURCES_YAML_CONTENTS)
        swift_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_object_client',
            return_value=self.swift)
        swift_patcher.start()
        self.addCleanup(swift_patcher.stop)

        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'get_orchestration_client')
    @mock.patch('tripleo_common.utils.config.Config.download_config')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_run(self, mock_create_tarball,
                 mock_config,
                 mock_orchestration_client):
        heat = mock.MagicMock()
        heat.stacks.get.return_value = mock.MagicMock(
            stack_name='stack', id='stack_id')
        mock_orchestration_client.return_value = heat
        mock_config.return_value = '/tmp/fake-path'

        action = config.GetOvercloudConfig(self.plan, '/tmp',
                                           self.config_container)
        action.run(self.ctx)

        self.swift.put_object.assert_called_once()
        mock_create_tarball.assert_called_once()


class DownloadConfigActionTest(base.TestCase):

    def setUp(self,):
        super(DownloadConfigActionTest, self).setUp()
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
                {'name': tf} for tf in self.template_files
            ]
        )
        self.swift.get_object.return_value = ({}, RESOURCES_YAML_CONTENTS)
        swift_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_object_client',
            return_value=self.swift)
        swift_patcher.start()
        self.addCleanup(swift_patcher.stop)

        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.utils.swift.download_container')
    @mock.patch('tempfile.mkdtemp')
    def test_run(self, mock_mkdtemp,
                 mock_swiftutils):
        action = config.DownloadConfigAction(self.config_container)
        action.run(self.ctx)
        mock_swiftutils.assert_called_once_with(self.swift,
                                                self.config_container,
                                                mock_mkdtemp())
