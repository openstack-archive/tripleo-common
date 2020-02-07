# Copyright 2017 Red Hat, Inc.
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

import os
import sys

import mock
from swiftclient import exceptions as swiftexceptions
import yaml

from tripleo_common.actions import container_images
from tripleo_common.tests import base


image_entries = [{
    'imagename': 't/cb-nova-compute:liberty',
    'params': ['ContainerNovaComputeImage', 'ContainerNovaLibvirtConfigImage']
}, {
    'imagename': 't/cb-nova-libvirt:liberty',
    'params': ['ContainerNovaLibvirtImage']
}]


class PrepareContainerImageEnvTest(base.TestCase):

    def setUp(self):
        super(PrepareContainerImageEnvTest, self).setUp()
        self.ctx = mock.MagicMock()

    @mock.patch("tripleo_common.actions.container_images."
                "PrepareContainerImageEnv.get_object_client")
    @mock.patch("tripleo_common.utils.plan."
                "update_plan_environment")
    @mock.patch("tripleo_common.image.kolla_builder.KollaImageBuilder")
    def test_run(self, kib, mock_update_plan, goc):
        swift = goc.return_value
        builder = kib.return_value
        builder.container_images_from_template.return_value = image_entries
        final_env = {'environments': [
            {'path': 'overcloud-resource-registry-puppet.yaml'},
            {'path': 'environments/containers-default-parameters.yaml'},
            {'path': 'user-environment.yaml'}
        ]}
        mock_update_plan.return_value = final_env

        action = container_images.PrepareContainerImageEnv(
            container='overcloud')
        self.assertEqual(final_env, action.run(self.ctx))

        kib.assert_called_once_with(
            [os.path.join(sys.prefix, 'share', 'tripleo-common',
                          'container-images', 'overcloud_containers.yaml.j2')]
        )
        params = {
            'ContainerNovaComputeImage': 't/cb-nova-compute:liberty',
            'ContainerNovaLibvirtConfigImage': 't/cb-nova-compute:liberty',
            'ContainerNovaLibvirtImage': 't/cb-nova-libvirt:liberty',
        }
        expected_env = yaml.safe_dump(
            {'parameter_defaults': params},
            default_flow_style=False
        )
        swift.put_object.assert_called_once_with(
            'overcloud',
            'environments/containers-default-parameters.yaml',
            expected_env
        )
        mock_update_plan.assert_called_once_with(
            swift,
            {'environments/containers-default-parameters.yaml': True},
            container='overcloud'
        )

    @mock.patch("tripleo_common.actions.container_images."
                "PrepareContainerImageEnv.get_object_client")
    @mock.patch("tripleo_common.utils.plan."
                "update_plan_environment")
    @mock.patch("tripleo_common.image.kolla_builder.KollaImageBuilder")
    def test_run_failed(self, kib, mock_update_plan, goc):
        swift = goc.return_value
        builder = kib.return_value
        builder.container_images_from_template.return_value = image_entries
        final_env = {'environments': [
            {'path': 'overcloud-resource-registry-puppet.yaml'},
            {'path': 'environments/containers-default-parameters.yaml'},
            {'path': 'user-environment.yaml'}
        ]}
        mock_update_plan.return_value = final_env

        action = container_images.PrepareContainerImageEnv(
            container='overcloud')
        self.assertEqual(final_env, action.run(self.ctx))

        mock_update_plan.side_effect = swiftexceptions.ClientException('ouch')
        self.assertEqual(
            'Error updating environment for plan overcloud: ouch',
            action.run(self.ctx).error
        )

        swift.put_object.side_effect = swiftexceptions.ClientException('nope')
        self.assertEqual(
            'Error updating environments/containers-default-parameters.yaml '
            'for plan overcloud: nope',
            action.run(self.ctx).error
        )
