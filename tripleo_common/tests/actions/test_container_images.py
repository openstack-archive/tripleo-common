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

from mistral_lib import actions
from tripleo_common.actions import container_images
from tripleo_common.image import kolla_builder
from tripleo_common.tests import base


image_entries = [{
    'imagename': 't/cb-nova-compute:liberty',
    'params': ['DockerNovaComputeImage', 'DockerNovaLibvirtConfigImage']
}, {
    'imagename': 't/cb-nova-libvirt:liberty',
    'params': ['DockerNovaLibvirtImage']
}]


class PrepareContainerImageEnvTest(base.TestCase):

    def setUp(self):
        super(PrepareContainerImageEnvTest, self).setUp()
        self.ctx = mock.MagicMock()

    @mock.patch("tripleo_common.actions.container_images."
                "PrepareContainerImageEnv.get_object_client")
    @mock.patch("tripleo_common.actions.heat_capabilities."
                "UpdateCapabilitiesAction")
    @mock.patch("tripleo_common.image.kolla_builder.KollaImageBuilder")
    def test_run(self, kib, update_action, goc):
        swift = goc.return_value
        builder = kib.return_value
        builder.container_images_from_template.return_value = image_entries
        final_env = {'environments': [
            {'path': 'overcloud-resource-registry-puppet.yaml'},
            {'path': 'environments/containers-default-parameters.yaml'},
            {'path': 'user-environment.yaml'}
        ]}
        update_action.return_value.run.return_value = final_env

        action = container_images.PrepareContainerImageEnv(
            container='overcloud')
        self.assertEqual(final_env, action.run(self.ctx))

        kib.assert_called_once_with(
            [os.path.join(sys.prefix, 'share', 'tripleo-common',
                          'container-images', 'overcloud_containers.yaml.j2')]
        )
        params = {
            'DockerNovaComputeImage': 't/cb-nova-compute:liberty',
            'DockerNovaLibvirtConfigImage': 't/cb-nova-compute:liberty',
            'DockerNovaLibvirtImage': 't/cb-nova-libvirt:liberty',
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
        update_action.assert_called_once_with(
            {'environments/containers-default-parameters.yaml': True},
            container='overcloud'
        )

    @mock.patch("tripleo_common.actions.container_images."
                "PrepareContainerImageEnv.get_object_client")
    @mock.patch("tripleo_common.actions.heat_capabilities."
                "UpdateCapabilitiesAction")
    @mock.patch("tripleo_common.image.kolla_builder.KollaImageBuilder")
    def test_run_failed(self, kib, update_action, goc):
        swift = goc.return_value
        builder = kib.return_value
        builder.container_images_from_template.return_value = image_entries
        final_env = {'environments': [
            {'path': 'overcloud-resource-registry-puppet.yaml'},
            {'path': 'environments/containers-default-parameters.yaml'},
            {'path': 'user-environment.yaml'}
        ]}
        update_action.return_value.run.return_value = final_env

        action = container_images.PrepareContainerImageEnv(
            container='overcloud')
        self.assertEqual(final_env, action.run(self.ctx))

        update_action.return_value.run.return_value = actions.Result(
            error='Error updating environment for plan overcloud: ouch')
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


class PrepareContainerImageParametersTest(base.TestCase):

    def setUp(self):
        super(PrepareContainerImageParametersTest, self).setUp()
        self.ctx = mock.MagicMock()

    @mock.patch("tripleo_common.actions.container_images."
                "PrepareContainerImageParameters._get_role_data")
    @mock.patch("tripleo_common.actions.container_images."
                "PrepareContainerImageParameters.get_object_client")
    @mock.patch("tripleo_common.actions.heat_capabilities."
                "UpdateCapabilitiesAction")
    @mock.patch("tripleo_common.utils.plan.get_env", autospec=True)
    @mock.patch("tripleo_common.image.kolla_builder."
                "container_images_prepare_multi")
    @mock.patch("tripleo_common.image.kolla_builder.KollaImageBuilder")
    def test_run(self, kib, prepare, get_env, update_action, goc, grd):
        builder = kib.return_value
        builder.container_images_from_template.return_value = image_entries
        plan = {
            'version': '1.0',
            'environments': [],
            'parameter_defaults': {}
        }
        role_data = [{'name': 'Controller'}]
        final_env = {'environments': [
            {'path': 'overcloud-resource-registry-puppet.yaml'},
            {'path': 'environments/containers-default-parameters.yaml'},
            {'path': 'user-environment.yaml'}
        ]}
        image_params = {
            'FooContainerImage': '192.0.2.1/foo/image',
            'DockerNovaComputeImage': 't/cb-nova-compute:liberty',
            'DockerNovaLibvirtConfigImage': 't/cb-nova-compute:liberty',
            'DockerNovaLibvirtImage': 't/cb-nova-libvirt:liberty',
        }
        image_env_contents = yaml.safe_dump(
            {'parameter_defaults': image_params},
            default_flow_style=False
        )

        swift = goc.return_value
        swift.get_object.return_value = role_data
        prepare.return_value = image_params
        grd.return_value = role_data

        get_env.return_value = plan
        update_action.return_value.run.return_value = final_env
        action = container_images.PrepareContainerImageParameters(
            container='overcloud')
        self.assertEqual(final_env, action.run(self.ctx))

        get_env.assert_called_once_with(swift, 'overcloud')
        prepare.assert_called_once_with({}, role_data, dry_run=True)
        swift.put_object.assert_called_once_with(
            'overcloud',
            'environments/containers-default-parameters.yaml',
            image_env_contents
        )


class ContainerImagePrepareDefaultTest(base.TestCase):

    def setUp(self):
        super(ContainerImagePrepareDefaultTest, self).setUp()
        self.ctx = mock.MagicMock()

    def test_empty(self):
        action = container_images.ContainerImagePrepareDefault({})
        result = action.run(self.ctx)

        self.assertEqual(
            result['ContainerImagePrepare'],
            kolla_builder.CONTAINER_IMAGE_PREPARE_PARAM
        )

    def test_some_values(self):
        values = {
            'tag_from_label': 'tag label',
            'push_destination': True,
            'namespace': 'namespace',
            'name_prefix': 'prefix-',
            'name_suffix': '-suffix',
            'tag': 'tag'
        }
        action = container_images.ContainerImagePrepareDefault(values)
        result = action.run(self.ctx)

        self.assertTrue('ContainerImagePrepare' in result)
        self.assertEqual(1, len(result['ContainerImagePrepare']))

        self.assertTrue('tag_from_label' in result['ContainerImagePrepare'][0])
        self.assertEqual(
            'tag label',
            result['ContainerImagePrepare'][0]['tag_from_label']
        )

        self.assertTrue(
            'push_destination' in result['ContainerImagePrepare'][0]
        )
        self.assertEqual(
            True,
            result['ContainerImagePrepare'][0]['push_destination']
        )

        self.assertTrue('set' in result['ContainerImagePrepare'][0])
        self.assertTrue(
            isinstance(result['ContainerImagePrepare'][0]['set'], dict)
        )

        s = result['ContainerImagePrepare'][0]['set']

        self.assertEqual(s['namespace'], 'namespace')
        self.assertEqual(s['name_prefix'], 'prefix-')
        self.assertEqual(s['name_suffix'], '-suffix')
        self.assertEqual(s['tag'], 'tag')
