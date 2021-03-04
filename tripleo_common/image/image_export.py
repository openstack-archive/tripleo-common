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
import errno
import hashlib
import json
import os
import requests
import six
import shutil

from oslo_log import log as logging
from tripleo_common.utils import image as image_utils

LOG = logging.getLogger(__name__)


IMAGE_EXPORT_DIR = '/var/lib/image-serve'

MEDIA_TYPES = (
    MEDIA_MANIFEST_V1,
    MEDIA_MANIFEST_V1_SIGNED,
    MEDIA_MANIFEST_V2,
    MEDIA_MANIFEST_V2_LIST,
) = (
    'application/vnd.docker.distribution.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v1+prettyjws',
    'application/vnd.docker.distribution.manifest.v2+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
)

TYPE_KEYS = (
    TYPE_KEY_URI,
    TYPE_KEY_TYPE
) = (
    'URI',
    'Content-Type'
)

TYPE_MAP_EXTENSION = '.type-map'


def skip_if_exists(f):
    @six.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except OSError as e:
            # Handle race for the already existing entity
            if e.errno == errno.EEXIST:
                pass
            else:
                raise e
    return wrapper


@skip_if_exists
def make_dir(path):
    if os.path.exists(path):
        return
    os.makedirs(path, 0o775)


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


@skip_if_exists
def export_stream(target_url, layer, layer_stream, verify_digest=True):
    image, _ = image_tag_from_url(target_url)
    digest = layer['digest']
    blob_dir_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image, 'blobs')
    make_dir(blob_dir_path)
    blob_path = os.path.join(blob_dir_path, '%s.gz' % digest)

    LOG.debug('[%s] Export layer to %s' % (image, blob_path))

    length = 0
    calc_digest = hashlib.sha256()

    def remove_layer(image, blob_path):
        if os.path.isfile(blob_path):
            os.remove(blob_path)
            LOG.error('[%s] Broken layer found and removed %s' %
                      (image, blob_path))

    try:
        fd = os.open(blob_path, os.O_WRONLY | os.O_CREAT)
        os.fchmod(fd, 0o0644)
        with open(fd, 'wb') as f:
            count = 0
            for chunk in layer_stream:
                count += 1
                if not chunk:
                    break
                LOG.debug('[%s] Writing chunk %i for %s' %
                          (image, count, digest))
                f.write(chunk)
                calc_digest.update(chunk)
                length += len(chunk)
                LOG.debug('[%s] Written %i bytes for %s' %
                          (image, length, digest))
    except MemoryError as e:
        memory_error = '[{}] Memory Error: {}'.format(image, str(e))
        LOG.error(memory_error)
        remove_layer(image, blob_path)
        raise MemoryError(memory_error)
    except requests.exceptions.HTTPError as e:
        # catch http errors seperately as those can be retried in
        # the image uploader
        http_error = '[{}] HTTP error: {}'.format(image, str(e))
        LOG.error(http_error)
        remove_layer(image, blob_path)
        raise
    except Exception as e:
        write_error = '[{}] Write Failure: {}'.format(image, str(e))
        LOG.error(write_error)
        remove_layer(image, blob_path)
        raise IOError(write_error)
    else:
        LOG.info('[%s] Layer written successfully %s' % (image, blob_path))

    layer_digest = 'sha256:%s' % calc_digest.hexdigest()
    LOG.debug('[%s] Provided digest: %s, Calculated digest: %s' %
              (image, digest, layer_digest))

    if verify_digest:
        if digest != layer_digest:
            hash_request_id = hashlib.sha1(str(target_url.geturl()).encode())
            error_msg = (
                '[%s] Image ID: %s, Expected digest "%s" does not match'
                ' calculated digest "%s", Blob path "%s". Blob'
                ' path will be cleaned up.' % (
                    image,
                    hash_request_id.hexdigest(),
                    digest,
                    layer_digest,
                    blob_path
                )
            )
            LOG.error(error_msg)
            if os.path.isfile(blob_path):
                os.remove(blob_path)
            raise requests.exceptions.HTTPError(error_msg)
    else:
        # if the original layer is uncompressed
        # the digest may change on export
        expected_blob_path = os.path.join(
            blob_dir_path, '%s.gz' % layer_digest
        )
        if blob_path != expected_blob_path:
            os.rename(blob_path, expected_blob_path)
            blob_path = expected_blob_path

    layer['digest'] = layer_digest
    layer['size'] = length
    LOG.debug('[%s] Done exporting image layer %s' % (image, digest))
    return (layer_digest, blob_path)


@skip_if_exists
def layer_cross_link(layer, image, blob_path, target_image_url):
    target_image, _ = image_tag_from_url(target_image_url)
    target_dir_path = os.path.join(
        IMAGE_EXPORT_DIR, 'v2', target_image, 'blobs')
    make_dir(target_dir_path)
    target_blob_path = os.path.join(target_dir_path, '%s.gz' % layer)
    if not os.path.exists(target_blob_path):
        LOG.debug('[%s] Linking layers: %s -> %s' %
                  (image, blob_path, target_blob_path))
        # make a hard link so the layers can have independent lifecycles
        os.link(blob_path, target_blob_path)


def cross_repo_mount(target_image_url, image_layers, source_layers,
                     uploaded_layers=None):
    linked_layers = {}
    target_image, _ = image_tag_from_url(target_image_url)
    for layer in source_layers:
        known_path, ref_image = image_utils.uploaded_layers_details(
            uploaded_layers, layer, scope='local')

        if layer not in image_layers and not ref_image:
            continue

        image_url = image_layers.get(layer, None)
        if image_url:
            image, _ = image_tag_from_url(image_url)
        else:
            image = ref_image
        if not image:
            continue

        if known_path and ref_image:
            blob_path = known_path
            image = ref_image
            if ref_image != image:
                LOG.debug('[%s] Layer ref. by image %s already exists '
                          'at %s' % (image, ref_image, known_path))
            else:
                LOG.debug('[%s] Layer already exists at %s'
                          % (image, known_path))
        else:
            dir_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image, 'blobs')
            blob_path = os.path.join(dir_path, '%s.gz' % layer)
            if not os.path.exists(blob_path):
                LOG.debug('[%s] Layer not found: %s' % (image, blob_path))
                continue

        layer_cross_link(layer, image, blob_path, target_image_url)
        linked_layers.update({layer: {'known_path': blob_path,
                                      'ref_image': image}})
    return linked_layers


def export_manifest_config(target_url,
                           manifest_str,
                           manifest_type,
                           config_str,
                           multi_arch=False):
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

    manifest_dict = {}
    if multi_arch:
        if manifest_type == MEDIA_MANIFEST_V2_LIST:
            manifest_dict[manifest_type] = manifest_digest
            # choose one of the entries to be the default v2 manifest
            # to return:
            # - If architecture amd64 exists, choose that
            # - Otherwise choose the first entry
            entries = manifest.get('manifests')
            if entries:
                entry = None
                for i in entries:
                    if i.get('platform', {}).get('architecture') == 'amd64':
                        entry = i
                        break
                if not entry:
                    entry = entries[0]
                manifest_dict[entry['mediaType']] = entry['digest']

    else:
        manifest_dict[manifest_type] = manifest_digest

    if manifest_dict:
        write_type_map_file(image, tag, manifest_dict)
    build_tags_list(image)


def write_type_map_file(image, tag, manifest_dict):
    manifests_path = os.path.join(
        IMAGE_EXPORT_DIR, 'v2', image, 'manifests')
    type_map_path = os.path.join(manifests_path, '%s%s' %
                                 (tag, TYPE_MAP_EXTENSION))
    with open(type_map_path, 'w+') as f:
        f.write('URI: %s\n\n' % tag)
        for manifest_type, digest in manifest_dict.items():
            f.write('Content-Type: %s\n' % manifest_type)
            f.write('URI: %s/index.json\n\n' % digest)


def parse_type_map_file(type_map_path):
    uri = None
    content_type = None
    type_map = {}
    with open(type_map_path, 'r') as f:
        for x in f:
            line = x[:-1]
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
    write_type_map_file(image, tag, {MEDIA_MANIFEST_V2: manifest_digest})
    os.remove(manifest_symlink_path)


def build_tags_list(image):
    manifests_path = os.path.join(
        IMAGE_EXPORT_DIR, 'v2', image, 'manifests')
    tags_dir_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image, 'tags')
    tags_list_path = os.path.join(tags_dir_path, 'list')
    LOG.debug('[%s] Rebuilding %s' % (image, tags_dir_path))
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
    metadata_set = set(['blobs', 'manifests', 'tags'])

    for namespace in os.listdir(images_path):
        namespace_path = os.path.join(images_path, namespace)
        if not os.path.isdir(namespace_path):
            continue
        contents_set = set(os.listdir(namespace_path))
        # handle containers with no namespaces
        if metadata_set.issubset(contents_set):
            catalog_entries.append(namespace)
        for image in list(contents_set - metadata_set):
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
        LOG.debug('[%s] Deleting legacy tag symlink %s' %
                  (image, manifest_symlink_path))
        os.remove(manifest_symlink_path)

    type_map_path = os.path.join(manifests_path, '%s%s' %
                                 (tag, TYPE_MAP_EXTENSION))
    if os.path.exists(type_map_path):
        LOG.debug('[%s] Deleting typemap file %s' % (image, type_map_path))
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
        LOG.debug('[%s] Deleting manifest %s' % (image, manifest_dir))
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
        LOG.debug('[%s] Deleting layer blob %s' % (image, blob))
        os.remove(blob)

    # if no files left in manifests_path, delete the whole image
    remaining = os.listdir(manifests_path)
    if not remaining or remaining == ['.htaccess']:
        image_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image)
        LOG.debug('[%s] Deleting image directory %s' % (image, image_path))
        shutil.rmtree(image_path)

    # rebuild the catalog for the current image list
    build_catalog()
