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
import six
import subprocess
import sys
import tempfile
import yaml

from tripleo_common.image import kolla_builder as kb
from tripleo_common.tests import base


filedata = six.u("""container_images:
- imagename: tripleoupstream/heat-docker-agents-centos:latest
  push_destination: localhost:8787
- imagename: tripleoupstream/centos-binary-nova-compute:liberty
  uploader: docker
  pull_source: docker.io
  push_destination: localhost:8787
- imagename: tripleoupstream/centos-binary-nova-libvirt:liberty
  uploader: docker
  pull_source: docker.io
- imagename: tripleoupstream/image-with-missing-tag
  push_destination: localhost:8787
""")

template_filedata = six.u("""
{% set namespace=namespace or "tripleoupstream" %}
{% set name_prefix=name_prefix or "centos-binary-" %}
{% set name_suffix=name_suffix or "" %}
{% set tag=tag or "latest" %}
container_images_template:
- imagename: "{{namespace}}/heat-docker-agents-centos:latest"
  push_destination: "{{push_destination}}"
- imagename: "{{namespace}}/{{name_prefix}}nova-compute{{name_suffix}}:{{tag}}"
  uploader: "docker"
  pull_source: "{{pull_source}}"
  push_destination: "{{push_destination}}"
- imagename: "{{namespace}}/{{name_prefix}}nova-libvirt{{name_suffix}}:{{tag}}"
  uploader: "docker"
  pull_source: "{{pull_source}}"
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
        self.assertEqual('foo', itr('foo:latest'))
        self.assertEqual('foo', itr('tripleo/foo:latest'))
        self.assertEqual('foo', itr('tripleo/foo'))
        self.assertEqual('foo', itr('tripleo/centos-binary-foo:latest'))
        self.assertEqual('foo', itr('centos-binary-foo:latest'))
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
            pull_source='docker.io',
            push_destination='localhost:8787',
            tag='liberty'
        )
        # template substitution on the container_images_template section should
        # be identical to the container_images section
        container_images = yaml.safe_load(filedata)['container_images']
        self.assertEqual(container_images, result)

    def test_container_images_from_template_filter(self):
        builder = kb.KollaImageBuilder(self.filelist)

        def filter(entry):

            # do not want heat-agents image
            if 'heat-docker-agents' in entry.get('imagename'):
                return

            # set source and destination on all entries
            entry['pull_source'] = 'docker.io'
            entry['push_destination'] = 'localhost:8787'
            return entry

        result = builder.container_images_from_template(
            filter=filter,
            tag='liberty'
        )
        container_images = [{
            'imagename': 'tripleoupstream/centos-binary-nova-compute:liberty',
            'pull_source': 'docker.io',
            'push_destination': 'localhost:8787',
            'uploader': 'docker'
        }, {
            'imagename': 'tripleoupstream/centos-binary-nova-libvirt:liberty',
            'pull_source': 'docker.io',
            'push_destination': 'localhost:8787',
            'uploader': 'docker'
        }, {
            'imagename': 'tripleoupstream/image-with-missing-tag',
            'pull_source': 'docker.io',
            'push_destination': 'localhost:8787'
        }]
        self.assertEqual(container_images, result)

    def test_container_images_yaml_in_sync(self):
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

        result = tmpl_builder.container_images_from_template(filter=ffunc)

        oc_yaml_file = os.path.join(files_dir, 'overcloud_containers.yaml')
        yaml_builder = kb.KollaImageBuilder([oc_yaml_file])
        container_images = yaml_builder.load_config_files(
            yaml_builder.CONTAINER_IMAGES)
        # remove odl related image references from overcloud_containers.yaml
        container_images.remove({'imagename': 'tripleopike/centos-binary'
                                              '-neutron-server-opendaylight:'
                                              'current-tripleo'})
        container_images.remove({'imagename': 'tripleopike/centos-binary'
                                              '-opendaylight:current-tripleo'})
        self.assertSequenceEqual(container_images, result)

    def test_container_images_yaml_in_sync_for_odl(self):
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
            neutron_driver='odl', filter=ffunc)

        oc_yaml_file = os.path.join(files_dir, 'overcloud_containers.yaml')
        yaml_builder = kb.KollaImageBuilder([oc_yaml_file])
        container_images = yaml_builder.load_config_files(
            yaml_builder.CONTAINER_IMAGES)
        # remove neutron-server image reference from overcloud_containers.yaml
        container_images.remove({'imagename': 'tripleopike/centos-binary'
                                              '-neutron-server:'
                                              'current-tripleo'})
        self.assertSequenceEqual(container_images, result)
