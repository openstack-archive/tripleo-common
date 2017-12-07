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

import socket

from six.moves import urllib

from tripleo_common import constants


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


def bracket_ipv6(address):
    """Put a bracket around address if it is valid IPv6

    Return it unchanged if it is a hostname or IPv4 address.
    """
    try:
        socket.inet_pton(socket.AF_INET6, address)
        return "[%s]" % address
    except socket.error:
        return address

CLEAR_ENV = """# Clear any old environment that may conflict.
for key in $( set | awk '{FS=\"=\"}  /^OS_/ {print $1}' ); do unset $key ; done
"""
CLOUDPROMPT = """
# Add OS_CLOUDNAME to PS1
if [ -z "${CLOUDPROMPT_ENABLED:-}" ]; then
    export PS1=${PS1:-""}
    export PS1=\${OS_CLOUDNAME:+"(\$OS_CLOUDNAME)"}\ $PS1
    export CLOUDPROMPT_ENABLED=1
fi
"""


def create_overcloudrc(stack, no_proxy, admin_password):
    """Given the stack and proxy settings, create the overcloudrc

    stack: Heat stack containing the deployed overcloud
    no_proxy: a comma-separated string of hosts that shouldn't be proxied
    """
    overcloud_endpoint = get_overcloud_endpoint(stack)
    overcloud_host = urllib.parse.urlparse(overcloud_endpoint).hostname
    overcloud_admin_vip = get_endpoint('KeystoneAdmin', stack)

    no_proxy_list = map(bracket_ipv6,
                        [no_proxy, overcloud_host, overcloud_admin_vip])

    rc_params = {
        'NOVA_VERSION': '1.1',
        'COMPUTE_API_VERSION': '1.1',
        'OS_USERNAME': 'admin',
        'OS_PROJECT_NAME': 'admin',
        'OS_USER_DOMAIN_NAME': 'Default',
        'OS_PROJECT_DOMAIN_NAME': 'Default',
        'OS_NO_CACHE': 'True',
        'OS_CLOUDNAME': stack.stack_name,
        'no_proxy': ','.join(no_proxy_list),
        'PYTHONWARNINGS': ('"ignore:Certificate has no, ignore:A true '
                           'SSLContext object is not available"'),
        'OS_AUTH_TYPE': 'password',
        'OS_PASSWORD': admin_password,
        'OS_AUTH_URL': overcloud_endpoint.replace('/v2.0', '') + '/v3',
        'OS_IDENTITY_API_VERSION': '3',
        'OS_IMAGE_API_VERSION': constants.DEFAULT_IMAGE_API_VERSION,
        'OS_VOLUME_API_VERSION': constants.DEFAULT_VOLUME_API_VERSION,
    }

    overcloudrc = CLEAR_ENV
    for key, value in rc_params.items():
        line = "export %(key)s=%(value)s\n" % {'key': key, 'value': value}
        overcloudrc = overcloudrc + line
    overcloudrc = overcloudrc + CLOUDPROMPT

    return {
        "overcloudrc": overcloudrc,
        "overcloudrc.v3": overcloudrc
    }
