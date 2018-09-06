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
- imagename: docker.io/tripleorocky/heat-docker-agents-centos:latest
  push_destination: localhost:8787
- imagename: docker.io/tripleorocky/centos-binary-nova-compute:liberty
  uploader: docker
  push_destination: localhost:8787
- imagename: docker.io/tripleorocky/centos-binary-nova-libvirt:liberty
  uploader: docker
- imagename: docker.io/tripleorocky/image-with-missing-tag
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
                'namespace': 'docker.io/tripleorocky',
                'ceph_namespace': 'docker.io/ceph',
                'ceph_image': 'daemon',
                'ceph_tag': 'v3.0.3-stable-3.0-luminous-centos-7-x86_64',
                'name_prefix': 'centos-binary-',
                'name_suffix': '',
                'tag': 'current-tripleo',
                'neutron_driver': None,
                'openshift_namespace': 'docker.io/openshift',
                'openshift_tag': 'v3.9.0',
                'openshift_base_image': 'origin',
                'openshift_cockpit_namespace': 'docker.io/cockpit',
                'openshift_cockpit_image': 'kubernetes',
                'openshift_cockpit_tag': 'latest',
                'openshift_etcd_namespace': 'registry.fedoraproject.org'
                '/latest',
                'openshift_etcd_image': 'etcd',
                'openshift_etcd_tag': 'latest',
                'openshift_gluster_namespace': 'docker.io/gluster',
                'openshift_gluster_image': 'gluster-centos',
                'openshift_gluster_block_image': 'glusterblock-provisioner',
                'openshift_gluster_tag': 'latest',
                'openshift_heketi_namespace': 'docker.io/heketi',
                'openshift_heketi_image': 'heketi',
                'openshift_heketi_tag': 'latest',
            },
            builder.container_images_template_inputs()
        )

        self.assertEqual(
            {
                'namespace': '192.0.2.0:5000/tripleorocky',
                'ceph_namespace': 'docker.io/cephh',
                'ceph_image': 'ceph-daemon',
                'ceph_tag': 'latest',
                'name_prefix': 'prefix-',
                'name_suffix': '-suffix',
                'tag': 'rocky',
                'neutron_driver': 'ovn',
                'openshift_namespace': 'docker.io/openshift3',
                'openshift_tag': 'v3.10.0',
                'openshift_base_image': 'ose',
                'openshift_cockpit_namespace': 'docker.io/openshift-cockpit',
                'openshift_cockpit_image': 'cockpit',
                'openshift_cockpit_tag': 'cockpit-tag',
                'openshift_etcd_namespace': 'registry.access.redhat.com/rhel7',
                'openshift_etcd_image': 'openshift-etcd',
                'openshift_etcd_tag': 'etcd-tag',
                'openshift_gluster_namespace':
                'registry.access.redhat.com/rhgs3',
                'openshift_gluster_image': 'rhgs-server-rhel7',
                'openshift_gluster_block_image':
                'rhgs-gluster-block-prov-rhel7',
                'openshift_gluster_tag': 'gluster-tag',
                'openshift_heketi_namespace':
                'registry.access.redhat.com/rhgs3',
                'openshift_heketi_image': 'rhgs-volmanager-rhel7',
                'openshift_heketi_tag': 'heketi-tag',
            },
            builder.container_images_template_inputs(
                namespace='192.0.2.0:5000/tripleorocky',
                ceph_namespace='docker.io/cephh',
                ceph_image='ceph-daemon',
                ceph_tag='latest',
                name_prefix='prefix',
                name_suffix='suffix',
                tag='rocky',
                neutron_driver='ovn',
                openshift_namespace='docker.io/openshift3',
                openshift_tag='v3.10.0',
                openshift_base_image='ose',
                openshift_cockpit_namespace='docker.io/openshift-cockpit',
                openshift_cockpit_image='cockpit',
                openshift_cockpit_tag='cockpit-tag',
                openshift_etcd_namespace='registry.access.redhat.com/rhel7',
                openshift_etcd_image='openshift-etcd',
                openshift_etcd_tag='etcd-tag',
                openshift_gluster_namespace='registry.access.redhat.com/rhgs3',
                openshift_gluster_image='rhgs-server-rhel7',
                openshift_gluster_block_image='rhgs-gluster-block-prov-rhel7',
                openshift_gluster_tag='gluster-tag',
                openshift_heketi_namespace='registry.access.redhat.com/rhgs3',
                openshift_heketi_image='rhgs-volmanager-rhel7',
                openshift_heketi_tag='heketi-tag',
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
            'imagename': 'docker.io/tripleorocky/'
                         'centos-binary-nova-compute:liberty',
            'push_destination': 'localhost:8787',
            'uploader': 'docker'
        }, {
            'imagename': 'docker.io/tripleorocky/'
                         'centos-binary-nova-libvirt:liberty',
            'push_destination': 'localhost:8787',
            'uploader': 'docker'
        }, {
            'imagename': 'docker.io/tripleorocky/image-with-missing-tag',
            'push_destination': 'localhost:8787'
        }]
        self.assertEqual(container_images, result)

    def _test_container_images_yaml_in_sync_helper(self, neutron_driver=None,
                                                   remove_images=[]):
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
            filter=ffunc, neutron_driver=neutron_driver)

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
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-neutron-server-opendaylight:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-neutron-server-ovn:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-ovn-base:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-opendaylight:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-ovn-northd:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary-ovn-'
                          'controller:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary-ovn-'
                          'nb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary-ovn-'
                          'sb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-neutron-metadata-agent-ovn:current-tripleo'}]
        self._test_container_images_yaml_in_sync_helper(
            remove_images=remove_images)

    def test_container_images_yaml_in_sync_for_odl(self):
        # remove neutron-server image reference from overcloud_containers.yaml
        remove_images = [
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-neutron-server:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-neutron-server-ovn:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-ovn-base:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-ovn-northd:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary-ovn-'
                          'controller:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary-ovn-'
                          'nb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary-ovn-'
                          'sb-db-server:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-neutron-metadata-agent-ovn:current-tripleo'}]
        self._test_container_images_yaml_in_sync_helper(
            neutron_driver='odl', remove_images=remove_images)

    def test_container_images_yaml_in_sync_for_ovn(self):
        # remove neutron-server image reference from overcloud_containers.yaml
        remove_images = [
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-neutron-server:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-neutron-server-opendaylight:current-tripleo'},
            {'imagename': 'docker.io/tripleorocky/centos-binary'
                          '-opendaylight:current-tripleo'}]
        self._test_container_images_yaml_in_sync_helper(
            neutron_driver='ovn', remove_images=remove_images)


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
    def test_prepare_includes(self, mock_get):
        self.assertEqual({
            'container_images.yaml': [
                {'imagename': '192.0.2.0:8787/t/p-nova-libvirt:l'}
            ],
            'environments/containers-default-parameters.yaml': {
                'DockerNovaLibvirtImage': '192.0.2.0:8787/t/p-nova-libvirt:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                includes=['libvirt'],
                mapping_args={
                    'namespace': '192.0.2.0:8787/t',
                    'name_prefix': 'p',
                    'name_suffix': '',
                    'tag': 'l',
                }
            )
        )

    @mock.patch('requests.get')
    def test_prepare_includes_excludes(self, mock_get):
        # assert same result as includes only. includes trumps excludes
        self.assertEqual({
            'container_images.yaml': [
                {'imagename': '192.0.2.0:8787/t/p-nova-libvirt:l'}
            ],
            'environments/containers-default-parameters.yaml': {
                'DockerNovaLibvirtImage': '192.0.2.0:8787/t/p-nova-libvirt:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                includes=['libvirt'],
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
                'DockerNovaApiImage':
                '192.0.2.0:8787/t/p-nova-api:l',
                'DockerNovaConfigImage':
                '192.0.2.0:8787/t/p-nova-api:l',
                'DockerNovaMetadataConfigImage':
                u'192.0.2.0:8787/t/p-nova-api:l',
                'DockerNovaMetadataImage':
                '192.0.2.0:8787/t/p-nova-api:l'
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
    @mock.patch('tripleo_common.image.image_uploader.get_undercloud_registry')
    def test_prepare_push_dest_discover(self, mock_gur, mock_get):
        mock_gur.return_value = '192.0.2.0:8787'
        self.assertEqual({
            'container_images.yaml': [{
                'imagename': 'docker.io/t/p-nova-api:l',
                'push_destination': '192.0.2.0:8787',
            }],
            'environments/containers-default-parameters.yaml': {
                'DockerNovaApiImage':
                '192.0.2.0:8787/t/p-nova-api:l',
                'DockerNovaConfigImage':
                '192.0.2.0:8787/t/p-nova-api:l',
                'DockerNovaMetadataConfigImage':
                u'192.0.2.0:8787/t/p-nova-api:l',
                'DockerNovaMetadataImage':
                '192.0.2.0:8787/t/p-nova-api:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                service_filter=['OS::TripleO::Services::NovaApi'],
                push_destination=True,
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
                {'imagename': 't/p-neutron-server-ovn:l'},
                {'imagename': 't/p-ovn-controller:l'}
            ],
            'environments/containers-default-parameters.yaml': {
                'DockerNeutronApiImage': 't/p-neutron-server-ovn:l',
                'DockerNeutronConfigImage': 't/p-neutron-server-ovn:l',
                'DockerOvnControllerConfigImage': 't/p-ovn-controller:l',
                'DockerOvnControllerImage': 't/p-ovn-controller:l'
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                service_filter=[
                    'OS::TripleO::Services::NeutronServer',
                    'OS::TripleO::Services::OVNController'
                ],
                mapping_args={
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
                {'imagename': 't/neutron-server-opendaylight:l'},
                {'imagename': 't/opendaylight:l'}
            ],
            'environments/containers-default-parameters.yaml': {
                'DockerNeutronApiImage': 't/neutron-server-opendaylight:l',
                'DockerNeutronConfigImage': 't/neutron-server-opendaylight:l',
                'DockerOpendaylightApiImage': 't/opendaylight:l',
                'DockerOpendaylightConfigImage': 't/opendaylight:l',
            }},
            kb.container_images_prepare(
                template_file=TEMPLATE_PATH,
                output_env_file=constants.CONTAINER_DEFAULTS_ENVIRONMENT,
                output_images_file='container_images.yaml',
                service_filter=[
                    'OS::TripleO::Services::NeutronServer',
                    'OS::TripleO::Services::OpenDaylightApi'
                ],
                mapping_args={
                    'namespace': 't',
                    'name_prefix': '',
                    'name_suffix': '',
                    'tag': 'l',
                }
            )
        )

    def test_get_enabled_services_empty(self):
        self.assertEqual(
            set([]),
            kb.get_enabled_services({}, [])
        )

    def test_get_enabled_services_default_count(self):
        self.assertEqual(
            set([
                'OS::TripleO::Services::NeutronApi',
                'OS::TripleO::Services::NovaApi',
                'OS::TripleO::Services::NovaCompute'
            ]),
            kb.get_enabled_services({
                'parameter_defaults': {}
            }, [
                {
                    'name': 'Controller',
                    'CountDefault': 1,
                    'ServicesDefault': [
                        'OS::TripleO::Services::NeutronApi',
                        'OS::TripleO::Services::NovaApi'
                    ]
                }, {
                    'name': 'Compute',
                    'CountDefault': 1,
                    'ServicesDefault': [
                        'OS::TripleO::Services::NovaCompute'
                    ]
                }, {
                    'name': 'BlockStorage',
                    'ServicesDefault': [
                        'OS::TripleO::Services::Ntp'
                    ]
                }
            ])
        )

    def test_get_enabled_services(self):
        self.assertEqual(
            set([
                'OS::TripleO::Services::NeutronApi',
                'OS::TripleO::Services::NovaApi',
                'OS::TripleO::Services::NovaCompute',
                'OS::TripleO::Services::NovaLibvirt'
            ]),
            kb.get_enabled_services({
                'parameter_defaults': {
                    'ControllerCount': 1,
                    'ComputeCount': 1,
                    'BlockStorageCount': 0,
                    'ComputeServices': [
                        'OS::TripleO::Services::NovaCompute',
                        'OS::TripleO::Services::NovaLibvirt'
                    ]
                }
            }, [
                {
                    'name': 'Controller',
                    'CountDefault': 0,
                    'ServicesDefault': [
                        'OS::TripleO::Services::NeutronApi',
                        'OS::TripleO::Services::NovaApi'
                    ]
                }, {
                    'name': 'Compute',
                    'ServicesDefault': [
                        'OS::TripleO::Services::NovaCompute'
                    ]
                }, {
                    'name': 'BlockStorage',
                    'ServicesDefault': [
                        'OS::TripleO::Services::Ntp'
                    ]
                }
            ])
        )

    def test_build_service_filter(self):
        self.assertEqual(
            set([
                'OS::TripleO::Services::HeatApi',
                'OS::TripleO::Services::NovaApi',
                'OS::TripleO::Services::NovaCompute',
                'OS::TripleO::Services::OpenShift::Master',
                'OS::TripleO::Services::Kubernetes::Worker',
                'OS::TripleO::Services::SkydiveAgent',
            ]),
            kb.build_service_filter({
                'resource_registry': {
                    'OS::TripleO::Services::NeutronApi':
                    '/tht/puppet/services/foo.yaml',
                    'OS::TripleO::Services::NovaApi':
                    '/tht/docker/services/foo.yaml',
                    'OS::TripleO::Services::NovaCompute':
                    '/tht/docker/services/foo.yaml',
                    'OS::TripleO::Services::OpenShift::Master':
                    'extraconfig/services/openshift-master.yaml',
                    'OS::TripleO::Services::Kubernetes::Worker':
                    'extraconfig/services/kubernetes-worker.yaml',
                    'OS::TripleO::Services::SkydiveAgent':
                    'extraconfig/services/skydive-agent.yaml',
                    'OS::TripleO::Services::Noop':
                    'OS::Heat::None'
                }
            }, [
                {
                    'name': 'Controller',
                    'CountDefault': 1,
                    'ServicesDefault': [
                        'OS::TripleO::Services::HeatApi',
                        'OS::TripleO::Services::NeutronApi',
                        'OS::TripleO::Services::NovaApi',
                        'OS::TripleO::Services::OpenShift::Master',
                        'OS::TripleO::Services::SkydiveAgent',
                        'OS::TripleO::Services::Noop'
                    ]
                }, {
                    'name': 'Compute',
                    'CountDefault': 1,
                    'ServicesDefault': [
                        'OS::TripleO::Services::NovaCompute',
                        'OS::TripleO::Services::Kubernetes::Worker'
                    ]
                }, {
                    'name': 'BlockStorage',
                    'ServicesDefault': [
                        'OS::TripleO::Services::Ntp'
                    ]
                }
            ])
        )

    @mock.patch('tripleo_common.image.kolla_builder.container_images_prepare')
    @mock.patch('tripleo_common.image.image_uploader.ImageUploadManager',
                autospec=True)
    def test_container_images_prepare_multi(self, mock_im, mock_cip):
        mapping_args = {
            'namespace': 't',
            'name_prefix': '',
            'name_suffix': '',
            'tag': 'l',
        }
        env = {
            'parameter_defaults': {
                'LocalContainerRegistry': '192.0.2.1',
                'ContainerImagePrepare': [{
                    'set': mapping_args,
                    'tag_from_label': 'foo',
                    'includes': ['nova', 'neutron'],
                }, {
                    'set': mapping_args,
                    'tag_from_label': 'bar',
                    'excludes': ['nova', 'neutron'],
                    'push_destination': True,
                    'modify_role': 'add-foo-plugin',
                    'modify_only_with_labels': ['kolla_version'],
                    'modify_vars': {'foo_version': '1.0.1'}
                }]
            }
        }
        roles_data = []
        mock_cip.side_effect = [
            {
                'image_params': {
                    'FooImage': 't/foo:latest',
                    'BarImage': 't/bar:latest',
                    'BazImage': 't/baz:latest',
                    'BinkImage': 't/bink:latest'
                },
                'upload_data': []
            }, {
                'image_params': {
                    'BarImage': 't/bar:1.0',
                    'BazImage': 't/baz:1.0'
                },
                'upload_data': [{
                    'imagename': 't/bar:1.0',
                    'push_destination': '192.0.2.1:8787'
                }, {
                    'imagename': 't/baz:1.0',
                    'push_destination': '192.0.2.1:8787'
                }]
            },
        ]

        image_params = kb.container_images_prepare_multi(env, roles_data)

        mock_cip.assert_has_calls([
            mock.call(
                excludes=None,
                includes=['nova', 'neutron'],
                mapping_args=mapping_args,
                output_env_file='image_params',
                output_images_file='upload_data',
                pull_source=None,
                push_destination=None,
                service_filter=None,
                tag_from_label='foo',
                append_tag=mock.ANY,
                modify_role=None,
                modify_only_with_labels=None,
                modify_vars=None
            ),
            mock.call(
                excludes=['nova', 'neutron'],
                includes=None,
                mapping_args=mapping_args,
                output_env_file='image_params',
                output_images_file='upload_data',
                pull_source=None,
                push_destination='192.0.2.1:8787',
                service_filter=None,
                tag_from_label='bar',
                append_tag=mock.ANY,
                modify_role='add-foo-plugin',
                modify_only_with_labels=['kolla_version'],
                modify_vars={'foo_version': '1.0.1'}
            )
        ])

        mock_im.assert_called_once()

        self.assertEqual(
            {
                'BarImage': 't/bar:1.0',
                'BazImage': 't/baz:1.0',
                'BinkImage': 't/bink:latest',
                'FooImage': 't/foo:latest'
            },
            image_params
        )

    @mock.patch('tripleo_common.image.kolla_builder.container_images_prepare')
    @mock.patch('tripleo_common.image.image_uploader.ImageUploadManager',
                autospec=True)
    def test_container_images_prepare_multi_dry_run(self, mock_im, mock_cip):
        mapping_args = {
            'namespace': 't',
            'name_prefix': '',
            'name_suffix': '',
            'tag': 'l',
        }
        env = {
            'parameter_defaults': {
                'ContainerImagePrepare': [{
                    'set': mapping_args,
                    'tag_from_label': 'foo',
                }, {
                    'set': mapping_args,
                    'tag_from_label': 'bar',
                    'excludes': ['nova', 'neutron'],
                    'push_destination': '192.0.2.1:8787',
                    'modify_role': 'add-foo-plugin',
                    'modify_only_with_labels': ['kolla_version'],
                    'modify_vars': {'foo_version': '1.0.1'},
                    'modify_append_tag': 'modify-123'
                }]
            }
        }
        roles_data = []
        mock_cip.side_effect = [
            {
                'image_params': {
                    'FooImage': 't/foo:latest',
                    'BarImage': 't/bar:latest',
                    'BazImage': 't/baz:latest',
                    'BinkImage': 't/bink:latest'
                },
                'upload_data': []
            }, {
                'image_params': {
                    'BarImage': 't/bar:1.0',
                    'BazImage': 't/baz:1.0'
                },
                'upload_data': [{
                    'imagename': 't/bar:1.0',
                    'push_destination': '192.0.2.1:8787'
                }, {
                    'imagename': 't/baz:1.0',
                    'push_destination': '192.0.2.1:8787'
                }]
            },
        ]

        image_params = kb.container_images_prepare_multi(env, roles_data, True)

        mock_cip.assert_has_calls([
            mock.call(
                excludes=None,
                includes=None,
                mapping_args=mapping_args,
                output_env_file='image_params',
                output_images_file='upload_data',
                pull_source=None,
                push_destination=None,
                service_filter=None,
                tag_from_label='foo',
                append_tag=mock.ANY,
                modify_role=None,
                modify_only_with_labels=None,
                modify_vars=None
            ),
            mock.call(
                excludes=['nova', 'neutron'],
                includes=None,
                mapping_args=mapping_args,
                output_env_file='image_params',
                output_images_file='upload_data',
                pull_source=None,
                push_destination='192.0.2.1:8787',
                service_filter=None,
                tag_from_label='bar',
                append_tag=mock.ANY,
                modify_role='add-foo-plugin',
                modify_only_with_labels=['kolla_version'],
                modify_vars={'foo_version': '1.0.1'}
            )
        ])

        mock_im.assert_called_once_with(mock.ANY, dry_run=True, verbose=True,
                                        cleanup='full')

        self.assertEqual(
            {
                'BarImage': 't/bar:1.0',
                'BazImage': 't/baz:1.0',
                'BinkImage': 't/bink:latest',
                'FooImage': 't/foo:latest'
            },
            image_params
        )
