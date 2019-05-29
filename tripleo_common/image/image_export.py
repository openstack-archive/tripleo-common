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

import collections
import hashlib
import json
import os
import shutil

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


IMAGE_EXPORT_DIR = '/var/lib/image-serve'

MEDIA_TYPES = (
    MEDIA_MANIFEST_V1,
    MEDIA_MANIFEST_V1_SIGNED,
    MEDIA_MANIFEST_V2,
) = (
    'application/vnd.docker.distribution.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v1+prettyjws',
    'application/vnd.docker.distribution.manifest.v2+json',
)

TYPE_KEYS = (
    TYPE_KEY_URI,
    TYPE_KEY_TYPE
) = (
    'URI',
    'Content-Type'
)

TYPE_MAP_EXTENSION = '.type-map'


def make_dir(path):
    if os.path.exists(path):
        return
    try:
        os.makedirs(path, 0o775)
    except os.error:
        # Handle race for directory already existing
        pass


def image_tag_from_url(image_url):
    parts = image_url.path.split(':')
    if len(parts) == 1:
        tag = None
        image = parts[0]
    else:
        tag = parts[-1]
        image = ':'.join(parts[:-1])

    # strip leading slash
    if image.startswith('/'):
        image = image[1:]

    return image, tag


def export_stream(target_url, layer, layer_stream, verify_digest=True):
    image, tag = image_tag_from_url(target_url)
    digest = layer['digest']
    blob_dir_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image, 'blobs')
    make_dir(blob_dir_path)
    blob_path = os.path.join(blob_dir_path, '%s.gz' % digest)

    LOG.debug('export layer to %s' % blob_path)

    length = 0
    calc_digest = hashlib.sha256()
    try:
        with open(blob_path, 'w+b') as f:
            for chunk in layer_stream:
                if not chunk:
                    break
                f.write(chunk)
                calc_digest.update(chunk)
                length += len(chunk)

        layer_digest = 'sha256:%s' % calc_digest.hexdigest()
        LOG.debug('Calculated layer digest: %s' % layer_digest)

        if verify_digest:
            if digest != layer_digest:
                raise IOError('Expected digest %s '
                              'does not match calculated %s' %
                              (digest, layer_digest))
        else:
            # if the original layer is uncompressed
            # the digest may change on export
            expected_blob_path = os.path.join(
                blob_dir_path, '%s.gz' % layer_digest)
            if blob_path != expected_blob_path:
                os.rename(blob_path, expected_blob_path)

    except Exception as e:
        LOG.error('Error while writing blob %s' % blob_path)
        # cleanup blob file
        if os.path.isfile(blob_path):
            os.remove(blob_path)
        raise e

    layer['digest'] = layer_digest
    layer['size'] = length
    return layer_digest


def cross_repo_mount(target_image_url, image_layers, source_layers):
    for layer in source_layers:
        if layer not in image_layers:
            continue

        image_url = image_layers[layer]
        image, tag = image_tag_from_url(image_url)
        dir_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image, 'blobs')
        blob_path = os.path.join(dir_path, '%s.gz' % layer)
        if not os.path.exists(blob_path):
            LOG.debug('Layer not found: %s' % blob_path)
            continue

        target_image, tag = image_tag_from_url(target_image_url)
        target_dir_path = os.path.join(
            IMAGE_EXPORT_DIR, 'v2', target_image, 'blobs')
        make_dir(target_dir_path)
        target_blob_path = os.path.join(target_dir_path, '%s.gz' % layer)
        if os.path.exists(target_blob_path):
            continue
        LOG.debug('Linking layers: %s -> %s' % (blob_path, target_blob_path))
        # make a hard link so the layers can have independent lifecycles
        os.link(blob_path, target_blob_path)


def export_manifest_config(target_url,
                           manifest_str,
                           manifest_type,
                           config_str):
    image, tag = image_tag_from_url(target_url)
    manifest = json.loads(manifest_str)
    if config_str is not None:
        blob_dir_path = os.path.join(
            IMAGE_EXPORT_DIR, 'v2', image, 'blobs')
        make_dir(blob_dir_path)
        config_digest = manifest['config']['digest']
        config_path = os.path.join(blob_dir_path, config_digest)

        with open(config_path, 'w+b') as f:
            f.write(config_str.encode('utf-8'))

    calc_digest = hashlib.sha256()
    calc_digest.update(manifest_str.encode('utf-8'))
    manifest_digest = 'sha256:%s' % calc_digest.hexdigest()

    manifests_path = os.path.join(
        IMAGE_EXPORT_DIR, 'v2', image, 'manifests')
    manifests_htaccess_path = os.path.join(manifests_path, '.htaccess')
    manifest_dir_path = os.path.join(manifests_path, manifest_digest)
    manifest_path = os.path.join(manifest_dir_path, 'index.json')
    htaccess_path = os.path.join(manifest_dir_path, '.htaccess')

    make_dir(manifest_dir_path)
    build_catalog()

    with open(manifests_htaccess_path, 'w+') as f:
        f.write('AddHandler type-map %s\n' % TYPE_MAP_EXTENSION)
        f.write('MultiviewsMatch Handlers\n')

    headers = collections.OrderedDict()
    headers['Content-Type'] = manifest_type
    headers['Docker-Content-Digest'] = manifest_digest
    headers['ETag'] = manifest_digest
    with open(htaccess_path, 'w+') as f:
        for header in headers.items():
            f.write('Header set %s "%s"\n' % header)

    with open(manifest_path, 'w+b') as f:
        manifest_data = manifest_str.encode('utf-8')
        f.write(manifest_data)

    write_type_map_file(image, tag, manifest_digest)
    build_tags_list(image)


def write_type_map_file(image, tag, manifest_digest):
    manifests_path = os.path.join(
        IMAGE_EXPORT_DIR, 'v2', image, 'manifests')
    type_map_path = os.path.join(manifests_path, '%s%s' %
                                 (tag, TYPE_MAP_EXTENSION))
    with open(type_map_path, 'w+') as f:
        f.write('URI: %s\n\n' % tag)
        f.write('Content-Type: %s\n' % MEDIA_MANIFEST_V2)
        f.write('URI: %s/index.json\n\n' % manifest_digest)


def parse_type_map_file(type_map_path):
    uri = None
    content_type = None
    type_map = {}
    with open(type_map_path, 'r') as f:
        for l in f:
            line = l[:-1]
            if not line:
                if uri and content_type:
                    type_map[content_type] = uri
                uri = None
                content_type = None
            else:
                key, value = line.split(': ')
                if key == TYPE_KEY_URI:
                    uri = value
                elif key == TYPE_KEY_TYPE:
                    content_type = value
    return type_map


def migrate_to_type_map_file(image, manifest_symlink_path):
    tag = os.path.split(manifest_symlink_path)[-1]
    manifest_dir = os.readlink(manifest_symlink_path)
    manifest_digest = os.path.split(manifest_dir)[-1]
    write_type_map_file(image, tag, manifest_digest)
    os.remove(manifest_symlink_path)


def build_tags_list(image):
    manifests_path = os.path.join(
        IMAGE_EXPORT_DIR, 'v2', image, 'manifests')
    tags_dir_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image, 'tags')
    tags_list_path = os.path.join(tags_dir_path, 'list')
    LOG.debug('Rebuilding %s' % tags_dir_path)
    make_dir(tags_dir_path)
    tags = []
    for f in os.listdir(manifests_path):
        f_path = os.path.join(manifests_path, f)
        if os.path.islink(f_path):
            tags.append(f)
            migrate_to_type_map_file(image, f_path)
        if f.endswith(TYPE_MAP_EXTENSION):
            tags.append(f[:-len(TYPE_MAP_EXTENSION)])

    tags_data = {
        "name": image,
        "tags": tags
    }
    with open(tags_list_path, 'w+b') as f:
        f.write(json.dumps(tags_data, ensure_ascii=False).encode('utf-8'))


def build_catalog():
    catalog_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', '_catalog')
    catalog_entries = []
    LOG.debug('Rebuilding %s' % catalog_path)
    images_path = os.path.join(IMAGE_EXPORT_DIR, 'v2')

    for namespace in os.listdir(images_path):
        namespace_path = os.path.join(images_path, namespace)
        if not os.path.isdir(namespace_path):
            continue
        for image in os.listdir(namespace_path):
            catalog_entries.append('%s/%s' % (namespace, image))

    catalog = {'repositories': catalog_entries}
    with open(catalog_path, 'w+b') as f:
        f.write(json.dumps(catalog, ensure_ascii=False).encode('utf-8'))


def delete_image(image_url):
    image, tag = image_tag_from_url(image_url)
    manifests_path = os.path.join(
        IMAGE_EXPORT_DIR, 'v2', image, 'manifests')

    manifest_symlink_path = os.path.join(manifests_path, tag)
    if os.path.exists(manifest_symlink_path):
        LOG.debug('Deleting legacy tag symlink %s' % manifest_symlink_path)
        os.remove(manifest_symlink_path)

    type_map_path = os.path.join(manifests_path, '%s%s' %
                                 (tag, TYPE_MAP_EXTENSION))
    if os.path.exists(type_map_path):
        LOG.debug('Deleting typemap file %s' % type_map_path)
        os.remove(type_map_path)

    build_tags_list(image)

    # build list of manifest_dir_path without symlinks
    linked_manifest_dirs = set()
    manifest_dirs = set()
    for f in os.listdir(manifests_path):
        f_path = os.path.join(manifests_path, f)
        if f_path.endswith(TYPE_MAP_EXTENSION):
            for uri in parse_type_map_file(f_path).values():
                linked_manifest_dir = os.path.dirname(
                    os.path.join(manifests_path, uri))
                linked_manifest_dirs.add(linked_manifest_dir)
        elif os.path.isdir(f_path):
            manifest_dirs.add(f_path)

    delete_manifest_dirs = manifest_dirs.difference(linked_manifest_dirs)

    # delete list of manifest_dir_path without symlinks
    for manifest_dir in delete_manifest_dirs:
        LOG.debug('Deleting manifest %s' % manifest_dir)
        shutil.rmtree(manifest_dir)

    # load all remaining manifests and build the set of of in-use blobs,
    # delete any layer blob not in-use
    reffed_blobs = set()
    blobs_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image, 'blobs')

    def add_reffed_blob(digest):
        blob_path = os.path.join(blobs_path, digest)
        gz_blob_path = os.path.join(blobs_path, '%s.gz' % digest)
        if os.path.isfile(gz_blob_path):
            reffed_blobs.add(gz_blob_path)
        elif os.path.isfile(blob_path):
            reffed_blobs.add(blob_path)

    for manifest_dir in linked_manifest_dirs:
        manifest_path = os.path.join(manifest_dir, 'index.json')
        with open(manifest_path) as f:
            manifest = json.load(f)
        v1manifest = manifest.get('schemaVersion', 2) == 1

        if v1manifest:
            for layer in manifest.get('fsLayers', []):
                add_reffed_blob(layer.get('blobSum'))
        else:
            for layer in manifest.get('layers', []):
                add_reffed_blob(layer.get('digest'))
            add_reffed_blob(manifest.get('config', {}).get('digest'))

    all_blobs = set([os.path.join(blobs_path, b)
                     for b in os.listdir(blobs_path)])
    delete_blobs = all_blobs.difference(reffed_blobs)
    for blob in delete_blobs:
        LOG.debug('Deleting layer blob %s' % blob)
        os.remove(blob)

    # if no files left in manifests_path, delete the whole image
    remaining = os.listdir(manifests_path)
    if not remaining or remaining == ['.htaccess']:
        image_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image)
        LOG.debug('Deleting image directory %s' % image_path)
        shutil.rmtree(image_path)

    # rebuild the catalog for the current image list
    build_catalog()
