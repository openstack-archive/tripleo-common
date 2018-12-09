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

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


IMAGE_EXPORT_DIR = '/var/lib/image-serve'


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


def export_stream(target_url, layer, calc_digest, layer_stream):
    image, tag = image_tag_from_url(target_url)
    digest = layer['digest']
    blob_dir_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image, 'blobs')
    make_dir(blob_dir_path)
    blob_path = os.path.join(blob_dir_path, '%s.gz' % digest)

    LOG.debug('export layer to %s' % blob_path)

    length = 0
    with open(blob_path, 'w+b') as f:
        for chunk in layer_stream:
            if not chunk:
                break
            f.write(chunk)
            calc_digest.update(chunk)
            length += len(chunk)

    layer_digest = 'sha256:%s' % calc_digest.hexdigest()
    LOG.debug('Calculated layer digest: %s' % layer_digest)
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

        with open(config_path, 'w+') as f:
            f.write(config_str)

    calc_digest = hashlib.sha256()
    calc_digest.update(manifest_str.encode('utf-8'))
    manifest_digest = 'sha256:%s' % calc_digest.hexdigest()

    manifests_path = os.path.join(
        IMAGE_EXPORT_DIR, 'v2', image, 'manifests')
    manifest_dir_path = os.path.join(manifests_path, manifest_digest)
    manifest_symlink_path = os.path.join(manifests_path, tag)
    manifest_path = os.path.join(manifest_dir_path, 'index.json')
    htaccess_path = os.path.join(manifest_dir_path, '.htaccess')
    tags_dir_path = os.path.join(IMAGE_EXPORT_DIR, 'v2', image, 'tags')
    tags_list_path = os.path.join(tags_dir_path, 'list')

    make_dir(manifest_dir_path)
    make_dir(tags_dir_path)

    headers = collections.OrderedDict()
    headers['Content-Type'] = manifest_type
    headers['Docker-Content-Digest'] = manifest_digest
    headers['ETag'] = manifest_digest
    with open(htaccess_path, 'w+') as f:
        for header in headers.items():
            f.write('Header set %s "%s"\n' % header)

    with open(manifest_path, 'w+') as f:
        f.write(manifest_str)

    if os.path.exists(manifest_symlink_path):
        os.remove(manifest_symlink_path)
    os.symlink(manifest_dir_path, manifest_symlink_path)

    tags = []
    for f in os.listdir(manifests_path):
        f_path = os.path.join(manifests_path, f)
        if os.path.islink(f_path):
            tags.append(f)

    tags_data = {
        "name": image,
        "tags": tags
    }
    with open(tags_list_path, 'w+') as f:
        json.dump(tags_data, f)
