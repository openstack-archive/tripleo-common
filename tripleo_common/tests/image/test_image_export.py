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
import shutil
import six
from six.moves.urllib.parse import urlparse
import tempfile
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
            'digest': compressed_digest
        }
        calc_digest = hashlib.sha256()
        layer_stream = io.BytesIO(blob_compressed)
        layer_digest = image_export.export_stream(
            target_url, layer, calc_digest, layer_stream
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
        image_export.cross_repo_mount(target_url, image_layers, source_layers)
        self.assertFalse(os.path.exists(source_blob_path))
        self.assertFalse(os.path.exists(target_blob_path))

        image_export.make_dir(source_blob_dir)
        with open(source_blob_path, 'w') as f:
            f.write('blob')
        self.assertTrue(os.path.exists(source_blob_path))

        # call with existing source
        image_export.cross_repo_mount(target_url, image_layers, source_layers)
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

        manifest_str = json.dumps(manifest)
        calc_digest = hashlib.sha256()
        calc_digest.update(manifest_str.encode('utf-8'))
        manifest_digest = 'sha256:%s' % calc_digest.hexdigest()

        image_export.export_manifest_config(
            target_url, manifest_str,
            image_uploader.MEDIA_MANIFEST_V2, config_str
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

        with open(config_path, 'r') as f:
            self.assertEqual(config_str, f.read())
        with open(manifest_path, 'r') as f:
            self.assertEqual(manifest_str, f.read())
        with open(manifest_htaccess_path, 'r') as f:
            self.assertEqual(expected_htaccess, f.read())
