# Copyright (c) 2021 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
from osc_lib import utils as osc_lib_utils


LOG = logging.getLogger(__name__)
heatclient = None


class EphemeralHeatClient(object):
    """A Heat client shim class to be used with ephemeral Heat.

    When the heat client is used to talk to the Heat API, the environment will
    be set with the correct variable configuration to configure Keystone for
    auth type none and to use a direct endpoint.

    After the client is finished, the environment is restored. This is
    necessary so that the entire system environment is not reconfigured for
    auth_type=none for the duration of the tripleoclient execution.

    :param heat: Heat client
    :type heat: `heatclient.heatclient`

    """

    def __init__(self, heat, host, port):
        self.heat = heat
        self.host = host
        self.port = port
        os.environ['OS_HEAT_TYPE'] = 'ephemeral'
        os.environ['OS_HEAT_HOST'] = host
        os.environ['OS_HEAT_PORT'] = str(port)

    def save_environment(self):
        self.environ = os.environ.copy()
        for v in ('OS_USER_DOMAIN_NAME',
                  'OS_PROJECT_DOMAIN_NAME',
                  'OS_PROJECT_NAME',
                  'OS_CLOUD'):
            os.environ.pop(v, None)

        os.environ['OS_AUTH_TYPE'] = "none"
        os.environ['OS_ENDPOINT'] = self.heat.http_client.endpoint

    def restore_environment(self):
        os.environ = self.environ.copy()

    def __getattr__(self, attr):
        self.save_environment()
        try:
            val = getattr(self.heat, attr)
        finally:
            self.restore_environment()
        return val


def local_orchestration_client(host="127.0.0.1", api_port=8006):
    """Returns a local orchestration service client"""

    API_VERSIONS = {
        '1': 'heatclient.v1.client.Client',
    }

    heat_client = osc_lib_utils.get_client_class(
        'tripleoclient',
        '1',
        API_VERSIONS)
    LOG.debug('Instantiating local_orchestration client for '
              'host %s, port %s: %s',
              host, api_port, heat_client)

    endpoint = 'http://%s:%s/v1/admin' % (host, api_port)
    client = heat_client(
        endpoint=endpoint,
        username='admin',
        password='fake',
        region_name='regionOne',
        token='fake',
    )

    global heatclient
    heatclient = EphemeralHeatClient(client, host, api_port)
    return heatclient
