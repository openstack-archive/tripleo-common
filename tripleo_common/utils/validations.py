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
import glob
import logging
import os
import re
import tempfile
import yaml

from oslo_concurrency import processutils

from tripleo_common import constants

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


def load_validations(groups=None):
    '''Loads all validations.'''
    paths = glob.glob('{}/*.yaml'.format(constants.DEFAULT_VALIDATIONS_PATH))
    results = []
    for validation_path in sorted(paths):
        with open(validation_path) as f:
            validation = yaml.safe_load(f.read())
            validation_groups = get_validation_metadata(validation, 'groups') \
                or []
            if not groups or \
                    set.intersection(set(groups), set(validation_groups)):
                results.append({
                    'id': os.path.splitext(
                        os.path.basename(validation_path))[0],
                    'name': get_validation_metadata(validation, 'name'),
                    'groups': get_validation_metadata(validation, 'groups'),
                    'description': get_validation_metadata(validation,
                                                           'description'),
                    'metadata': get_remaining_metadata(validation)
                })
    return results


def get_remaining_metadata(validation):
    try:
        return {k: v for k, v in validation[0]['vars']['metadata'].items()
                if k not in ['name', 'description', 'groups']}
    except KeyError:
        return dict()


def find_validation(validation):
    return '{}/{}.yaml'.format(constants.DEFAULT_VALIDATIONS_PATH, validation)


def run_validation(validation, identity_file, plan, context):
    return processutils.execute(
        '/usr/bin/sudo', '-u', 'validations',
        'OS_AUTH_URL={}'.format(context.auth_uri),
        'OS_USERNAME={}'.format(context.user_name),
        'OS_AUTH_TOKEN={}'.format(context.auth_token),
        'OS_TENANT_NAME={}'.format(context.project_name),
        '/usr/bin/run-validation',
        find_validation(validation),
        identity_file,
        plan
    )


def write_identity_file(key):
    """Write the SSH private key to disk"""
    fd, path = tempfile.mkstemp(prefix='validations_identity_')
    LOG.debug('Writing SSH key to disk at %s', path)
    with os.fdopen(fd, 'w') as tmp:
        tmp.write(key)
    processutils.execute('/usr/bin/sudo', '/usr/bin/chown', 'validations:',
                         path)
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
