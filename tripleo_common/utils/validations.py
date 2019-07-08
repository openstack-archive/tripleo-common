# Copyright 2016 Red Hat, Inc.
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
import logging
import os
import re
import tempfile
import yaml

from oslo_concurrency import processutils
from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
import tripleo_common.utils.swift as swift_utils

LOG = logging.getLogger(__name__)

DEFAULT_METADATA = {
    'name': 'Unnamed',
    'description': 'No description',
    'stage': 'No stage',
    'groups': [],
}


def get_validation_metadata(validation, key):
    try:
        return validation[0]['vars']['metadata'][key]
    except KeyError:
        return DEFAULT_METADATA.get(key)
    except TypeError:
        LOG.exception("Failed to get validation metadata.")


def _get_validations_from_swift(swift, container, objects, groups, results,
                                skip_existing=False):
    existing_ids = [validation['id'] for validation in results]

    for obj in objects:
        validation_id, ext = os.path.splitext(obj['name'])
        if ext != '.yaml':
            continue

        if skip_existing and validation_id in existing_ids:
            continue

        contents = swift_utils.get_object_string(swift, container, obj['name'])
        validation = yaml.safe_load(contents)
        validation_groups = get_validation_metadata(validation, 'groups') or []

        if not groups or set.intersection(set(groups), set(validation_groups)):
            results.append({
                'id': validation_id,
                'name': get_validation_metadata(validation, 'name'),
                'groups': get_validation_metadata(validation, 'groups'),
                'description': get_validation_metadata(validation,
                                                       'description'),
                'parameters': get_validation_parameters(validation)
            })

    return results


def load_validations(swift, plan, groups=None):
    """Loads all validations.

    Retrieves all of default and custom validations for a given plan and
    returns a list of dicts, with each dict representing a single validation.
    If both a default and a custom validation with the same name are found,
    the custom validation is picked.
    """
    results = []

    # Get custom validations first
    container = plan

    try:
        objects = swift.get_container(
            container, prefix=constants.CUSTOM_VALIDATIONS_FOLDER)[1]
    except swiftexceptions.ClientException:
        pass
    else:
        results = _get_validations_from_swift(
            swift, container, objects, groups, results)

    # Get default validations
    container = constants.VALIDATIONS_CONTAINER_NAME
    objects = swift.get_container(container)[1]
    results = _get_validations_from_swift(swift, container, objects, groups,
                                          results, skip_existing=True)

    return results


def get_validation_parameters(validation):
    try:
        return {
            k: v
            for k, v in validation[0]['vars'].items()
            if k != 'metadata'
        }
    except KeyError:
        return dict()


def download_validation(swift, plan, validation):
    """Downloads validations from Swift to a temporary location"""
    dst_dir = '/tmp/{}-validations'.format(plan)

    # Download the whole default validations container
    swift_utils.download_container(
        swift,
        constants.VALIDATIONS_CONTAINER_NAME,
        dst_dir,
        overwrite_only_newer=True
    )

    filename = '{}.yaml'.format(validation)
    swift_path = os.path.join(constants.CUSTOM_VALIDATIONS_FOLDER, filename)
    dst_path = os.path.join(dst_dir, filename)

    # If a custom validation with that name exists, get it from the plan
    # container and override. Otherwise, the default one will be used.
    try:
        contents = swift_utils.get_object_string(swift, plan, swift_path)
    except swiftexceptions.ClientException:
        pass
    else:
        with open(dst_path, 'w') as f:
            f.write(contents)

    return dst_path


def run_validation(swift, validation, identity_file,
                   plan, inputs_file, context):
    return processutils.execute(
        '/usr/bin/sudo', '-u', 'validations',
        'OS_AUTH_URL={}'.format(context.auth_uri),
        'OS_USERNAME={}'.format(context.user_name),
        'OS_AUTH_TOKEN={}'.format(context.auth_token),
        'OS_TENANT_NAME={}'.format(context.project_name),
        '/usr/bin/run-validation',
        '--inputs', inputs_file,
        download_validation(swift, plan, validation),
        identity_file,
        plan,
        constants.DEFAULT_VALIDATIONS_BASEDIR
    )


def write_identity_file(key):
    """Write the SSH private key to disk"""
    fd, path = tempfile.mkstemp(prefix='validations_identity_')
    LOG.debug('Writing SSH key to disk at %s', path)
    with os.fdopen(fd, 'w') as tmp:
        tmp.write(key)
    processutils.execute('/usr/bin/sudo', '/usr/bin/chown', '-h',
                         'validations:', path)
    return path


def cleanup_identity_file(path):
    """Remove the SSH private key from disk"""
    LOG.debug('Cleaning up identity file at %s', path)
    processutils.execute('/usr/bin/sudo', '/usr/bin/rm', '-f', path)


def pattern_validator(pattern, value):
    LOG.debug('Validating %s with pattern %s', value, pattern)
    if not re.match(pattern, value):
        return False
    return True


def write_inputs_file(inputs):
    """Serialise the validation inputs to a file on disk."""
    fd, path = tempfile.mkstemp(prefix='validations_inputs_')
    LOG.debug("Writing the validation inputs to %s", path)
    with os.fdopen(fd, 'w') as tmp:
        tmp.write(yaml.dump(inputs))
    processutils.execute('/usr/bin/sudo',
                         '/usr/bin/chown',
                         '-h',
                         'validations:',
                         path)
    return path


def cleanup_inputs_file(path):
    """Remove the temporary validation inputs file."""
    LOG.debug("Cleaning up the validation inputs at %s", path)
    processutils.execute('/usr/bin/sudo', '/usr/bin/rm', '-f', path)
