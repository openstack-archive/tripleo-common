#   Copyright 2018 Red Hat, Inc.
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

import hashlib
import io
import json
import os
import requests
import shutil
import six
from six.moves.urllib.parse import urlparse
import tempfile
from unittest import mock
import zlib

from tripleo_common.image import image_export
from tripleo_common.image import image_uploader
from tripleo_common.tests import base


class TestImageExport(base.TestCase):
    def setUp(self):
        super(TestImageExport, self).setUp()
        export_dir = image_export.IMAGE_EXPORT_DIR
        with tempfile.NamedTemporaryFile() as f:
            temp_export_dir = f.name
        image_export.make_dir(temp_export_dir)

        def restore_export_dir():
            shutil.rmtree(temp_export_dir)
            image_export.IMAGE_EXPORT_DIR = export_dir

        image_export.IMAGE_EXPORT_DIR = temp_export_dir
        self.addCleanup(restore_export_dir)

    def test_make_dir(self):

        path = os.path.join(image_export.IMAGE_EXPORT_DIR, 'foo/bar')

        self.assertFalse(os.path.exists(path))

        self.addCleanup(os.rmdir, path)
        image_export.make_dir(path)

        self.assertTrue(os.path.isdir(path))

        # Call again to assert no error is raised
        image_export.make_dir(path)

    def test_image_tag_from_url(self):
        url = urlparse('docker://docker.io/t/nova-api:latest')
        self.assertEqual(
            ('t/nova-api', 'latest'),
            image_export.image_tag_from_url(url)
        )
        url = urlparse('containers-storage:localhost:8787/t/nova-api:latest')
        self.assertEqual(
            ('localhost:8787/t/nova-api', 'latest'),
            image_export.image_tag_from_url(url)
        )

        url = urlparse('docker://docker.io/t/nova-api')
        self.assertEqual(
            ('t/nova-api', None),
            image_export.image_tag_from_url(url)
        )

    def test_export_stream(self):
        blob_data = six.b('The Blob')
        blob_compressed = zlib.compress(blob_data)
        calc_digest = hashlib.sha256()
        calc_digest.update(blob_compressed)
        compressed_digest = 'sha256:' + calc_digest.hexdigest()

        target_url = urlparse('docker://localhost:8787/t/nova-api:latest')
        layer = {
            'digest': 'sha256:somethingelse'
        }
        calc_digest = hashlib.sha256()
        layer_stream = io.BytesIO(blob_compressed)
        mask = os.umask(0o077)
        layer_digest, _ = image_export.export_stream(
            target_url, layer, layer_stream, verify_digest=False
        )
        self.assertEqual(compressed_digest, layer_digest)
        self.assertEqual(compressed_digest, layer['digest'])
        self.assertEqual(len(blob_compressed), layer['size'])

        blob_dir = os.path.join(image_export.IMAGE_EXPORT_DIR,
                                'v2/t/nova-api/blobs')
        blob_path = os.path.join(blob_dir, '%s.gz' % compressed_digest)

        self.assertTrue(os.path.isdir(blob_dir))
        self.assertTrue(os.path.isfile(blob_path))
        with open(blob_path, 'rb') as f:
            self.assertEqual(blob_compressed, f.read())

        os.umask(mask)
        blob_mode = oct(os.stat(blob_path).st_mode)
        self.assertEqual('644', blob_mode[-3:])

    @mock.patch('tripleo_common.image.image_export.open',
                side_effect=MemoryError())
    def test_export_stream_memory_error(self, mock_open):
        blob_data = six.b('The Blob')
        blob_compressed = zlib.compress(blob_data)
        calc_digest = hashlib.sha256()
        calc_digest.update(blob_compressed)

        target_url = urlparse('docker://localhost:8787/t/nova-api:latest')
        layer = {
            'digest': 'sha256:somethingelse'
        }
        calc_digest = hashlib.sha256()
        layer_stream = io.BytesIO(blob_compressed)
        self.assertRaises(MemoryError, image_export.export_stream,
                          target_url, layer, layer_stream, verify_digest=False)

    def test_export_stream_verify_failed(self):
        blob_data = six.b('The Blob')
        blob_compressed = zlib.compress(blob_data)
        calc_digest = hashlib.sha256()
        calc_digest.update(blob_compressed)

        target_url = urlparse('docker://localhost:8787/t/nova-api:latest')
        layer = {
            'digest': 'sha256:somethingelse'
        }
        calc_digest = hashlib.sha256()
        layer_stream = io.BytesIO(blob_compressed)
        self.assertRaises(requests.exceptions.HTTPError,
                          image_export.export_stream,
                          target_url, layer, layer_stream,
                          verify_digest=True)
        blob_dir = os.path.join(image_export.IMAGE_EXPORT_DIR,
                                'v2/t/nova-api/blobs')
        blob_path = os.path.join(blob_dir, 'sha256:somethingelse.gz')

        self.assertTrue(os.path.isdir(blob_dir))
        self.assertFalse(os.path.isfile(blob_path))

    def test_cross_repo_mount(self):
        target_url = urlparse('docker://localhost:8787/t/nova-api:latest')
        other_url = urlparse('docker://localhost:8787/t/nova-compute:latest')
        image_layers = {
            'sha256:1234': other_url
        }
        source_layers = [
            'sha256:1234', 'sha256:6789'
        ]
        source_blob_dir = os.path.join(image_export.IMAGE_EXPORT_DIR,
                                       'v2/t/nova-compute/blobs')
        source_blob_path = os.path.join(source_blob_dir, 'sha256:1234.gz')
        target_blob_dir = os.path.join(image_export.IMAGE_EXPORT_DIR,
                                       'v2/t/nova-api/blobs')
        target_blob_path = os.path.join(target_blob_dir, 'sha256:1234.gz')

        # call with missing source, no change
        image_export.cross_repo_mount(target_url, image_layers, source_layers,
                                      uploaded_layers={})
        self.assertFalse(os.path.exists(source_blob_path))
        self.assertFalse(os.path.exists(target_blob_path))

        image_export.make_dir(source_blob_dir)
        with open(source_blob_path, 'w') as f:
            f.write('blob')
        self.assertTrue(os.path.exists(source_blob_path))

        # call with existing source
        image_export.cross_repo_mount(target_url, image_layers, source_layers,
                                      uploaded_layers={})
        self.assertTrue(os.path.exists(target_blob_path))
        with open(target_blob_path, 'r') as f:
            self.assertEqual('blob', f.read())

    def test_export_manifest_config(self):
        target_url = urlparse('docker://localhost:8787/t/nova-api:latest')
        config_str = '{"config": {}}'
        config_digest = 'sha256:1234'
        manifest = {
            'config': {
                'digest': config_digest,
                'size': 2,
                'mediaType': 'application/vnd.docker.container.image.v1+json'
            },
            'layers': [
                {'digest': 'sha256:aeb786'},
                {'digest': 'sha256:4dc536'},
            ],
            'mediaType': 'application/vnd.docker.'
                         'distribution.manifest.v2+json',
        }
        catalog = {'repositories': ['t/nova-api']}

        manifest_str = json.dumps(manifest)
        calc_digest = hashlib.sha256()
        calc_digest.update(manifest_str.encode('utf-8'))
        manifest_digest = 'sha256:%s' % calc_digest.hexdigest()

        image_export.export_manifest_config(
            target_url, manifest_str,
            image_uploader.MEDIA_MANIFEST_V2, config_str
        )

        catalog_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            'v2/_catalog'
        )
        config_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            'v2/t/nova-api/blobs/sha256:1234'
        )
        manifest_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            'v2/t/nova-api/manifests',
            manifest_digest,
            'index.json'
        )
        manifest_htaccess_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            'v2/t/nova-api/manifests',
            manifest_digest,
            '.htaccess'
        )
        expected_htaccess = '''Header set Content-Type "%s"
Header set Docker-Content-Digest "%s"
Header set ETag "%s"
''' % (
            'application/vnd.docker.distribution.manifest.v2+json',
            manifest_digest,
            manifest_digest
        )

        with open(catalog_path, 'r') as f:
            self.assertEqual(catalog, json.load(f))
        with open(config_path, 'r') as f:
            self.assertEqual(config_str, f.read())
        with open(manifest_path, 'r') as f:
            self.assertEqual(manifest_str, f.read())
        with open(manifest_htaccess_path, 'r') as f:
            self.assertEqual(expected_htaccess, f.read())

    def test_write_parse_type_map_file(self):
        manifest_dir_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            'v2/foo/bar/manifests'
        )
        map_file_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            manifest_dir_path, 'latest.type-map'
        )

        image_export.make_dir(manifest_dir_path)
        image_export.write_type_map_file(
            'foo/bar',
            'latest',
            {image_export.MEDIA_MANIFEST_V2: 'sha256:1234abcd'}
        )

        expected_map_file = '''URI: latest

Content-Type: application/vnd.docker.distribution.manifest.v2+json
URI: sha256:1234abcd/index.json

'''
        # assert the file contains the expected content
        with open(map_file_path, 'r') as f:
            self.assertEqual(expected_map_file, f.read())

        # assert parse_type_map_file correctly reads that file
        self.assertEqual(
            {
                'application/vnd.docker.distribution.manifest.v2+json':
                'sha256:1234abcd/index.json'
            },
            image_export.parse_type_map_file(map_file_path)
        )

        # assert a multi-entry file is correctly parsed
        multi_map_file = '''URI: latest

Content-Type: application/vnd.docker.distribution.manifest.v2+json
URI: sha256:1234abcd/index.json

Content-Type: application/vnd.docker.distribution.manifest.list.v2+json
URI: sha256:eeeeeeee/index.json

'''
        with open(map_file_path, 'w+') as f:
            f.write(multi_map_file)
        self.assertEqual(
            {
                'application/vnd.docker.distribution.manifest.v2+json':
                'sha256:1234abcd/index.json',
                'application/vnd.docker.distribution.manifest.list.v2+json':
                'sha256:eeeeeeee/index.json'
            },
            image_export.parse_type_map_file(map_file_path)
        )

    def test_migrate_to_type_map_file(self):
        manifest_dir_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            'v2/foo/bar/manifests'
        )
        map_file_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            manifest_dir_path, 'latest.type-map'
        )
        symlink_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            manifest_dir_path, 'latest'
        )
        manifest_path = os.path.join(
            image_export.IMAGE_EXPORT_DIR,
            manifest_dir_path, 'sha256:1234abcd'
        )
        image_export.make_dir(manifest_dir_path)
        # create legacy symlink
        os.symlink(manifest_path, symlink_path)

        # run the migration
        image_export.migrate_to_type_map_file('foo/bar', symlink_path)

        expected_map_file = '''URI: latest

Content-Type: application/vnd.docker.distribution.manifest.v2+json
URI: sha256:1234abcd/index.json

'''
        # assert the migrated file contains the expected content
        with open(map_file_path, 'r') as f:
            self.assertEqual(expected_map_file, f.read())

    def _write_test_image(self, url, manifest):
        image, tag = image_uploader.BaseImageUploader._image_tag_from_url(
            url)
        blob_dir = os.path.join(
            image_export.IMAGE_EXPORT_DIR, 'v2', image[1:], 'blobs')
        image_export.make_dir(blob_dir)

        if manifest.get('schemaVersion', 2) == 1:
            config_str = None
            manifest_type = image_uploader.MEDIA_MANIFEST_V1
            layers = list(reversed([x['blobSum']
                                    for x in manifest['fsLayers']]))
        else:
            config_str = '{"config": {}}'
            manifest_type = image_uploader.MEDIA_MANIFEST_V2
            layers = [x['digest'] for x in manifest['layers']]
        manifest_str = json.dumps(manifest)
        calc_digest = hashlib.sha256()
        calc_digest.update(manifest_str.encode('utf-8'))
        manifest_digest = 'sha256:%s' % calc_digest.hexdigest()

        image_export.export_manifest_config(
            url, manifest_str, manifest_type, config_str
        )
        for digest in layers:
            blob_path = os.path.join(blob_dir, '%s.gz' % digest)

            with open(blob_path, 'w+') as f:
                f.write('The Blob')
        return manifest_digest

    def assertFiles(self, dirs, files, deleted):
        for d in dirs:
            self.assertTrue(os.path.isdir(d), 'is dir: %s' % d)
        for f in files:
            self.assertTrue(os.path.isfile(f), 'is file: %s' % f)
        for d in deleted:
            self.assertFalse(os.path.exists(d), 'deleted still exists: %s' % d)

    def test_delete_image(self):
        url1 = urlparse('docker://localhost:8787/t/nova-api:latest')
        url2 = urlparse('docker://localhost:8787/t/nova-api:abc')
        manifest_1 = {
            'schemaVersion': 1,
            'fsLayers': [
                {'blobSum': 'sha256:aeb786'},
                {'blobSum': 'sha256:4dc536'},
            ],
            'mediaType': 'application/vnd.docker.'
                         'distribution.manifest.v2+json',
        }
        manifest_2 = {
            'config': {
                'digest': 'sha256:5678',
                'size': 2,
                'mediaType': 'application/vnd.docker.container.image.v1+json'
            },
            'layers': [
                {'digest': 'sha256:aeb786'},  # shared with manifest_1
                {'digest': 'sha256:eeeeee'},  # different to manifest_1
            ],
            'mediaType': 'application/vnd.docker.'
                         'distribution.manifest.v2+json',
        }

        m1_digest = self._write_test_image(
            url=url1,
            manifest=manifest_1
        )
        m2_digest = self._write_test_image(
            url=url2,
            manifest=manifest_2
        )

        v2_dir = os.path.join(image_export.IMAGE_EXPORT_DIR, 'v2')
        image_dir = os.path.join(v2_dir, 't/nova-api')
        blob_dir = os.path.join(image_dir, 'blobs')
        m_dir = os.path.join(image_dir, 'manifests')

        # assert every directory and file for the 2 images
        self.assertFiles(
            dirs=[
                v2_dir,
                image_dir,
                blob_dir,
                m_dir,
                os.path.join(m_dir, m1_digest),
                os.path.join(m_dir, m2_digest),
            ],
            files=[
                os.path.join(m_dir, m1_digest, 'index.json'),
                os.path.join(m_dir, m2_digest, 'index.json'),
                os.path.join(blob_dir, 'sha256:aeb786.gz'),
                os.path.join(blob_dir, 'sha256:4dc536.gz'),
                os.path.join(blob_dir, 'sha256:5678'),
                os.path.join(blob_dir, 'sha256:eeeeee.gz'),
                os.path.join(m_dir, 'latest.type-map'),
                os.path.join(m_dir, 'abc.type-map'),
            ],
            deleted=[]
        )

        image_export.delete_image(url2)

        # assert files deleted for nova-api:abc
        self.assertFiles(
            dirs=[
                v2_dir,
                image_dir,
                blob_dir,
                m_dir,
                os.path.join(m_dir, m1_digest),
            ],
            files=[
                os.path.join(m_dir, m1_digest, 'index.json'),
                os.path.join(blob_dir, 'sha256:aeb786.gz'),
                os.path.join(blob_dir, 'sha256:4dc536.gz'),
                os.path.join(m_dir, 'latest.type-map'),
            ],
            deleted=[
                os.path.join(m_dir, 'abc'),
                os.path.join(m_dir, m2_digest),
                os.path.join(m_dir, m2_digest, 'index.json'),
                os.path.join(blob_dir, 'sha256:5678'),
                os.path.join(blob_dir, 'sha256:eeeeee.gz'),
            ]
        )

        image_export.delete_image(url1)

        # assert all nova-api files deleted after deleting the last image
        self.assertFiles(
            dirs=[
                v2_dir,
            ],
            files=[],
            deleted=[
                image_dir,
                blob_dir,
                m_dir,
                os.path.join(m_dir, 'abc'),
                os.path.join(m_dir, 'latest'),
                os.path.join(m_dir, m1_digest),
                os.path.join(m_dir, m1_digest, 'index.json'),
                os.path.join(m_dir, m2_digest),
                os.path.join(m_dir, m2_digest, 'index.json'),
                os.path.join(blob_dir, 'sha256:5678'),
                os.path.join(blob_dir, 'sha256:eeeeee.gz'),
                os.path.join(blob_dir, 'sha256:aeb786.gz'),
                os.path.join(blob_dir, 'sha256:4dc536.gz'),
            ]
        )
