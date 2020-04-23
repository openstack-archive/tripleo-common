#   Copyright 2015 Red Hat, Inc.
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

import logging

from heatclient import exc as heat_exc
from six.moves import urllib
from swiftclient import exceptions as swiftexceptions

from tripleo_common import constants
from tripleo_common.utils import common as common_utils
from tripleo_common.utils import plan as plan_utils

try:  # py3
    from shlex import quote
except ImportError:  # py2
    from pipes import quote

LOG = logging.getLogger(__name__)


def get_service_ips(stack):
    service_ips = {}
    for output in stack.to_dict().get('outputs', {}):
        service_ips[output['output_key']] = output['output_value']
    return service_ips


def get_endpoint_map(stack):
    endpoint_map = {}
    for output in stack.to_dict().get('outputs', {}):
        if output['output_key'] == 'EndpointMap':
            endpoint_map = output['output_value']
            break
    return endpoint_map


def get_endpoint(key, stack):
    endpoint_map = get_endpoint_map(stack)
    if endpoint_map:
        return endpoint_map[key]['host']
    else:
        return get_service_ips(stack).get(key + 'Vip')


def get_overcloud_endpoint(stack):
    for output in stack.to_dict().get('outputs', {}):
        if output['output_key'] == 'KeystoneURL':
            return output['output_value']


CLEAR_ENV = """# Clear any old environment that may conflict.
for key in $( set | awk '{FS=\"=\"}  /^OS_/ {print $1}' ); do unset $key ; done
"""
CLOUDPROMPT = """
# Add OS_CLOUDNAME to PS1
if [ -z "${CLOUDPROMPT_ENABLED:-}" ]; then
    export PS1=${PS1:-""}
    export PS1=\\${OS_CLOUDNAME:+"(\\$OS_CLOUDNAME)"}\\ $PS1
    export CLOUDPROMPT_ENABLED=1
fi
"""


def create_overcloudrc(swift, heat,
                       container=constants.DEFAULT_CONTAINER_NAME,
                       no_proxy=""):
    try:
        stack = heat.stacks.get(container)
    except heat_exc.HTTPNotFound:
        error = (
            "The Heat stack {} could not be found. Make sure you have "
            "deployed before calling this action.").format(container)
        raise RuntimeError(error)

    # We need to check parameter_defaults first for a user provided
    # password. If that doesn't exist, we then should look in the
    # automatically generated passwords.
    # TODO(d0ugal): Abstract this operation somewhere. We shouldn't need to
    # know about the structure of the environment to get a password.
    try:
        env = plan_utils.get_env(swift, container)
    except swiftexceptions.ClientException as err:
        err_msg = ("Error retrieving environment for plan %s: %s" % (
            container, err))
        LOG.error(err_msg)
        raise RuntimeError(err_msg)

    try:
        parameter_defaults = env['parameter_defaults']
        passwords = env['passwords']
        admin_pass = parameter_defaults.get('AdminPassword')
        if admin_pass is None:
            admin_pass = passwords['AdminPassword']
    except KeyError:
        error = ("Unable to find the AdminPassword in the plan "
                 "environment.")
        raise RuntimeError(error)

    region_name = parameter_defaults.get('KeystoneRegion')
    return _create_overcloudrc(stack, no_proxy,
                               admin_pass, region_name)


def _create_overcloudrc(stack, no_proxy, admin_password, region_name):
    """Given the stack and proxy settings, create the overcloudrc

    stack: Heat stack containing the deployed overcloud
    no_proxy: a comma-separated string of hosts that shouldn't be proxied
    """
    overcloud_endpoint = get_overcloud_endpoint(stack)
    overcloud_host = urllib.parse.urlparse(overcloud_endpoint).hostname
    overcloud_admin_vip = get_endpoint('KeystoneAdmin', stack)

    no_proxy_list = no_proxy.split(',')
    no_proxy_list = map(common_utils.bracket_ipv6,
                        no_proxy_list + [overcloud_host, overcloud_admin_vip])

    # Remove duplicated entries
    no_proxy_list = sorted(list(set(no_proxy_list)))

    rc_params = {
        'OS_USERNAME': 'admin',
        'OS_PROJECT_NAME': 'admin',
        'OS_USER_DOMAIN_NAME': 'Default',
        'OS_PROJECT_DOMAIN_NAME': 'Default',
        'OS_NO_CACHE': 'True',
        'OS_CLOUDNAME': stack.stack_name,
        'no_proxy': ','.join(no_proxy_list),
        'PYTHONWARNINGS': ('ignore:Certificate has no, ignore:A true '
                           'SSLContext object is not available'),
        'OS_AUTH_TYPE': 'password',
        'OS_PASSWORD': admin_password,
        'OS_AUTH_URL': overcloud_endpoint.replace('/v2.0', ''),
        'OS_IDENTITY_API_VERSION': constants.DEFAULT_IDENTITY_API_VERSION,
        'OS_COMPUTE_API_VERSION': constants.DEFAULT_COMPUTE_API_VERSION,
        'OS_IMAGE_API_VERSION': constants.DEFAULT_IMAGE_API_VERSION,
        'OS_VOLUME_API_VERSION': constants.DEFAULT_VOLUME_API_VERSION,
        'OS_REGION_NAME': region_name or 'regionOne'
    }

    overcloudrc = CLEAR_ENV
    for key, value in rc_params.items():
        line = "export %(key)s=%(value)s\n" % {'key': key,
                                               'value': quote(value)}
        overcloudrc = overcloudrc + line
    overcloudrc = overcloudrc + CLOUDPROMPT

    return {
        "overcloudrc": overcloudrc,
    }
