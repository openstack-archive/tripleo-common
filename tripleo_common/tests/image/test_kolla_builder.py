#   Copyright 2017 Red Hat, Inc.
#
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
#


import mock
import os
import requests
import six
import subprocess
import sys
import tempfile
import yaml

from tripleo_common import constants
from tripleo_common.image import kolla_builder as kb
from tripleo_common.tests import base


TEMPLATE_PATH = os.path.join(os.path.dirname(__file__),
                             '..', '..', '..', 'container-images',
                             'overcloud_containers.yaml.j2')


filedata = six.u("""container_images:
- imagename: docker.io/tripleomaster/heat-docker-agents-centos:latest
  push_destination: localhost:8787
- imagename: docker.io/tripleomaster/centos-binary-nova-compute:liberty
  uploader: docker
  push_destination: localhost:8787
- imagename: docker.io/tripleomaster/centos-binary-nova-libvirt:liberty
  uploader: docker
- imagename: docker.io/tripleomaster/image-with-missing-tag
  push_destination: localhost:8787
""")

template_filedata = six.u("""
container_images_template:
- imagename: "{{namespace}}/heat-docker-agents-centos:latest"
  push_destination: "{{push_destination}}"
- imagename: "{{namespace}}/{{name_prefix}}nova-compute{{name_suffix}}:{{tag}}"
  uploader: "docker"
  push_destination: "{{push_destination}}"
- imagename: "{{namespace}}/{{name_prefix}}nova-libvirt{{name_suffix}}:{{tag}}"
  uploader: "docker"
- imagename: "{{namespace}}/image-with-missing-tag"
  push_destination: "{{push_destination}}"
""")


class TestKollaImageBuilder(base.TestCase):

    def setUp(self):
        super(TestKollaImageBuilder, self).setUp()
        files = []
        files.append('testfile')
        self.filelist = files

    def test_imagename_to_regex(self):
        itr = kb.KollaImageBuilder.imagename_to_regex
        self.assertIsNone(itr(''))
        self.assertIsNone(itr(None))
        self.assertEqual('foo', itr('foo'))
        self.assertEqual('foo', itr('foo:current-tripleo'))
        self.assertEqual('foo', itr('tripleo/foo:current-tripleo'))
        self.assertEqual('foo', itr('tripleo/foo'))
        self.assertEqual('foo',
                         itr('tripleo/centos-binary-foo:current-tripleo'))
        self.assertEqual('foo', itr('centos-binary-foo:current-tripleo'))
        self.assertEqual('foo', itr('centos-binary-foo'))

    @mock.patch('tripleo_common.image.base.open',
                mock.mock_open(read_data=filedata), create=True)
    @mock.patch('os.path.isfile', return_value=True)
    @mock.patch('subprocess.Popen')
    def test_build_images(self, mock_popen, mock_path):
        process = mock.Mock()
        process.returncode = 0
        process.communicate.return_value = 'done', ''
        mock_popen.return_value = process

        builder = kb.KollaImageBuilder(self.filelist)
        self.assertEqual('done', builder.build_images(['kolla-config.conf']))
        env = os.environ.copy()
        mock_popen.assert_called_once_with([
            'kolla-build',
            '--config-file',
            'kolla-config.conf',
            'nova-compute',
            'nova-libvirt',
            'heat-docker-agents-centos',
            'image-with-missing-tag',
        ], env=env, stdout=-1)

    @mock.patch('subprocess.Popen')
    def test_build_images_no_conf(self, mock_popen):
        process = mock.Mock()
        process.returncode = 0
        process.communicate.return_value = 'done', ''
        mock_popen.return_value = process

        builder = kb.KollaImageBuilder([])
        self.assertEqual('done', builder.build_images([]))
        env = os.environ.copy()
        mock_popen.assert_called_once_with([
            'kolla-build',
        ], env=env, stdout=-1)

    @mock.patch('subprocess.Popen')
    def test_build_images_fail(self, mock_popen):
        process = mock.Mock()
        process.returncode = 1
        process.communicate.return_value = '', 'ouch'
        mock_popen.return_value = process

        builder = kb.KollaImageBuilder([])
        self.assertRaises(subprocess.CalledProcessError,
                          builder.build_images,
                          [])
        env = os.environ.copy()
        mock_popen.assert_called_once_with([
            'kolla-build',
        ], env=env, stdout=-1)


class TestKollaImageBuilderTemplate(base.TestCase):

    def setUp(self):
        super(TestKollaImageBuilderTemplate, self).setUp()
        with tempfile.NamedTemporaryFile(delete=False) as imagefile:
            self.addCleanup(os.remove, imagefile.name)
            self.filelist = [imagefile.name]
            with open(imagefile.name, 'w') as f:
                f.write(template_filedata)

    def test_container_images_from_template(self):
        builder = kb.KollaImageBuilder(self.filelist)
        result = builder.container_images_from_template(
            push_destination='localhost:8787',
            tag='liberty'
        )
        # template substitution on the container_images_template section should
        # be identical to the container_images section
        container_images = yaml.safe_load(filedata)['container_images']
        self.assertEqual(container_images, result)

    def test_container_images_template_inputs(self):
        builder = kb.KollaImageBuilder(self.filelist)
        self.assertEqual(
            kb.CONTAINER_IMAGES_DEFAULTS,
            builder.container_images_template_inputs()
        )

        self.assertEqual(
            {
                'namespace': 'docker.io/tripleomaster',
                'ceph_namespace': 'docker.io/ceph',
                'ceph_image': 'daemon',
                'ceph_tag': 'v3.0.3-stable-3.0-luminous-centos-7-x86_64',
                'logging': 'files',
                'name_prefix': 'centos-binary-',
                'name_suffix': '',
                'tag': 'current-tripleo',
                'neutron_driver': None
            },
            builder.container_images_template_inputs()
        )

        self.assertEqual(
            {
                'namespace': '192.0.2.0:5000/tripleomaster',
                'ceph_namespace': 'docker.io/cephh',
                'ceph_image': 'ceph-daemon',
                'ceph_tag': 'latest',
                'logging': 'stdout',
                'name_prefix': 'prefix-',
                'name_suffix': '-suffix',
                'tag': 'master',
                'neutron_driver': 'ovn'
            },
            builder.container_images_template_inputs(
                namespace='192.0.2.0:5000/tripleomaster',
                ceph_namespace='docker.io/cephh',
                ceph_image='ceph-daemon',
                ceph_tag='latest',
                name_prefix='prefix',
                name_suffix='suffix',
                tag='master',
                neutron_driver='ovn',
                logging='stdout'
            )
        )

    def test_container_images_from_template_filter(self):
        builder = kb.KollaImageBuilder(self.filelist)

        def filter(entry):

            # do not want heat-agents image
            if 'heat-docker-agents' in entry.get('imagename'):
                return

            # set source and destination on all entries
            entry['push_destination'] = 'localhost:8787'
            return entry

        result = builder.container_images_from_template(
            filter=filter,
            tag='liberty'
        )
        container_images = [{
            'imagename': 'docker.io/tripleomaster/'
                         'centos-binary-nova-compute:liberty',
            'push_destination': 'localhost:8787',
            'uploader': 'docker'
        }, {
            'imagename': 'docker.io/tripleomaster/'
                         'centos-binary-nova-libvirt:liberty',
            'push_destination': 'localhost:8787',
            'uploader': 'docker'
        }, {
            'imagename': 'docker.io/tripleomaster/image-with-missing-tag',
            'push_destination': 'localhost:8787'
        }]
        self.assertEqual(container_images, result)

    def _test_container_images_yaml_in_sync_helper(self, neutron_driver=None,
                                                   remove_images=[],
                                                   logging='files'):
        '''Confirm overcloud_containers.tpl.yaml equals overcloud_containers.yaml

        TODO(sbaker) remove when overcloud_containers.yaml is deleted
        '''
        mod_dir = os.path.dirname(sys.modules[__name__].__file__)
        project_dir = os.path.abspath(os.path.join(mod_dir, '../../../'))
        files_dir = os.path.join(project_dir, 'container-images')

        oc_tmpl_file = os.path.join(files_dir, 'overcloud_containers.yaml.j2')
        tmpl_builder = kb.KollaImageBuilder([oc_tmpl_file])

        def ffunc(entry):
            if 'params' in entry:
                del(entry['params'])
            if 'services' in entry:
                del(entry['services'])
            return entry

        result = tmpl_builder.container_images_from_template(
            filter=ffunc, neutron_driver=neutron_driver, logging=logging)

        oc_yaml_file = os.path.join(files_dir, 'overcloud_containers.yaml')
        yaml_builder = kb.KollaImageBuilder([oc_yaml_file])
        container_images = yaml_builder.load_config_files(
            yaml_builder.CONTAINER_IMAGES)

        # remove image references from overcloud_containers.yaml specified
        # in remove_images param.
        for image in remove_images:
            container_images.remove(image)

        self.assertSequenceEqual(container_images, result)

    def test_container_images_yaml_in_sync(self):
        remove_images = [
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-server-opendaylight:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-server-ovn:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-ovn-base:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-opendaylight:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-ovn-northd:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'controller:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'nb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'sb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-metadata-agent-ovn:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-rsyslog-base:current-tripleo'}]
        self._test_container_images_yaml_in_sync_helper(
            remove_images=remove_images)

    def test_container_images_yaml_in_sync_for_odl(self):
        # remove neutron-server image reference from overcloud_containers.yaml
        remove_images = [
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-server:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-server-ovn:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-ovn-base:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-ovn-northd:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'controller:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'nb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'sb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-metadata-agent-ovn:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-rsyslog-base:current-tripleo'}]
        self._test_container_images_yaml_in_sync_helper(
            neutron_driver='odl', remove_images=remove_images)

    def test_container_images_yaml_in_sync_for_ovn(self):
        # remove neutron-server image reference from overcloud_containers.yaml
        remove_images = [
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-server:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-server-opendaylight:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-opendaylight:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-rsyslog-base:current-tripleo'}]
        self._test_container_images_yaml_in_sync_helper(
            neutron_driver='ovn', remove_images=remove_images)

    def test_container_images_yaml_in_sync_for_stdout_logging(self):
        remove_images = [
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-server-opendaylight:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-server-ovn:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-ovn-base:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-opendaylight:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'northd:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'controller:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'nb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary-ovn-'
                          'sb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleomaster/centos-binary'
                          '-neutron-metadata-agent-ovn:current-tripleo'}]
        self._test_container_images_yaml_in_sync_helper(
            remove_images=remove_images, logging='stdout')


class TestPrepare(base.TestCase):

    def setUp(self):
        super(TestPrepare, self).setUp()
        with tempfile.NamedTemporaryFile(delete=False) as imagefile:
            self.addCleanup(os.remove, imagefile.name)
            self.filelist = [imagefile.name]
            with open(imagefile.name, 'w') as f:
                f.write(template_filedata)

    @mock.patch('requests.get')
    def test_detect_insecure_registry(self, mock_get):
        self.assertEqual(
            {},
            kb.detect_insecure_registries(
                {'foo': 'docker.io/tripleo'}))
        self.assertEqual(
            {},
            kb.detect_insecure_registries(
                {'foo': 'tripleo'}))

        mock_get.side_effect = requests.exceptions.ReadTimeout('ouch')
        self.assertEqual(
            {},
            kb.detect_insecure_registries(
                {'foo': '192.0.2.0:8787/tripleo'}))

        mock_get.side_effect = requests.exceptions.SSLError('ouch')
        self.assertEqual(
            {'DockerInsecureRegistryAddress': ['192.0.2.0:8787']},
            kb.detect_insecure_registries(
                {'foo': '192.0.2.0:8787/tripleo'}))

        self.assertEqual(
            {'DockerInsecureRegistryAddress': [
                '192.0.2.0:8787',
                '192.0.2.1:8787']},
            kb.detect_insecure_registries({
                'foo': '192.0.2.0:8787/tripleo/foo',
                'bar': '192.0.2.0:8787/tripleo/bar',
                'baz': '192.0.2.1:8787/tripleo/baz',
            }))

    @mock.patch('requests.get')
    def test_prepare_noargs(self, mock_get):
        self.assertEqual(
            {},
            kb.container_images_prepare(template_file=TEMPLATE_PATH)
        )

    @mock.patch('requests.get')
    def test_prepare_simple(self, mock_get):
        self.assertEqual({
            'container_images.yaml': [
                {'imagename': '192.0.2.0:8787/t/p-nova-compute:l'}
            ],
            'environments/containers-default-parameters.yaml': {
                'DockerNovaComputeImage': '192.0.2.0:8787/t/p-nova-compute:l',
                'DockerNovaLibvirtConfigImage': '192.0.2.0:8787/t/'
                                                'p-nova-compute:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                service_filter=['OS::TripleO::Services::NovaLibvirt'],
                excludes=['libvirt'],
                mapping_args={
                    'namespace': '192.0.2.0:8787/t',
                    'name_prefix': 'p',
                    'name_suffix': '',
                    'tag': 'l',
                }
            )
        )

    @mock.patch('requests.get')
    def test_prepare_push_dest(self, mock_get):
        self.assertEqual({
            'container_images.yaml': [{
                'imagename': 'docker.io/t/p-nova-api:l',
                'push_destination': '192.0.2.0:8787',
            }],
            'environments/containers-default-parameters.yaml': {
                'DockerNovaApiImage': '192.0.2.0:8787/t/p-nova-api:l',
                'DockerNovaConfigImage': '192.0.2.0:8787/t/p-nova-api:l',
                'DockerNovaMetadataImage': '192.0.2.0:8787/t/p-nova-api:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                service_filter=['OS::TripleO::Services::NovaApi'],
                push_destination='192.0.2.0:8787',
                mapping_args={
                    'namespace': 'docker.io/t',
                    'name_prefix': 'p',
                    'name_suffix': '',
                    'tag': 'l',
                }
            )
        )

    @mock.patch('requests.get')
    def test_prepare_ceph(self, mock_get):
        self.assertEqual({
            'container_images.yaml': [{
                'imagename': '192.0.2.0:8787/t/ceph:l',
            }],
            'environments/containers-default-parameters.yaml': {
                'DockerCephDaemonImage': '192.0.2.0:8787/t/ceph:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                service_filter=['OS::TripleO::Services::CephMon'],
                mapping_args={
                    'ceph_namespace': '192.0.2.0:8787/t',
                    'ceph_image': 'ceph',
                    'ceph_tag': 'l',
                }
            )
        )

    @mock.patch('requests.get')
    def test_prepare_neutron_driver_default(self, mock_get):
        self.assertEqual({
            'container_images.yaml': [
                {'imagename': 't/p-neutron-server:l'}
            ],
            'environments/containers-default-parameters.yaml': {
                'DockerNeutronApiImage': 't/p-neutron-server:l',
                'DockerNeutronConfigImage': 't/p-neutron-server:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                service_filter=['OS::TripleO::Services::NeutronServer'],
                mapping_args={
                    'namespace': 't',
                    'name_prefix': 'p',
                    'name_suffix': '',
                    'tag': 'l',
                }
            )
        )

    @mock.patch('requests.get')
    def test_prepare_neutron_driver_ovn(self, mock_get):
        self.assertEqual({
            'container_images.yaml': [
                {'imagename': 't/p-neutron-server-ovn:l'}
            ],
            'environments/containers-default-parameters.yaml': {
                'DockerNeutronApiImage': 't/p-neutron-server-ovn:l',
                'DockerNeutronConfigImage': 't/p-neutron-server-ovn:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                service_filter=['OS::TripleO::Services::NeutronServer'],
                mapping_args={
                    'neutron_driver': 'ovn',
                    'namespace': 't',
                    'name_prefix': 'p',
                    'name_suffix': '',
                    'tag': 'l',
                }
            )
        )

    @mock.patch('requests.get')
    def test_prepare_neutron_driver_odl(self, mock_get):
        self.assertEqual({
            'container_images.yaml': [
                {'imagename': 't/p-neutron-server-opendaylight:l'}
            ],
            'environments/containers-default-parameters.yaml': {
                'DockerNeutronApiImage': 't/p-neutron-server-opendaylight:l',
                'DockerNeutronConfigImage': 't/p-neutron-server-opendaylight:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                service_filter=['OS::TripleO::Services::NeutronServer'],
                mapping_args={
                    'neutron_driver': 'odl',
                    'namespace': 't',
                    'name_prefix': 'p',
                    'name_suffix': '',
                    'tag': 'l',
                }
            )
        )
