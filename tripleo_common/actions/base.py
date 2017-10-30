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
import json
import zlib

from glanceclient.v2 import client as glanceclient
from heatclient.v1 import client as heatclient
import ironic_inspector_client
from ironicclient.v1 import client as ironicclient
from mistral_lib import actions
from mistralclient.api import client as mistral_client
from novaclient.client import Client as nova_client
from swiftclient import client as swift_client
from swiftclient import exceptions as swiftexceptions
from zaqarclient.queues.v2 import client as zaqarclient

from tripleo_common import constants
from tripleo_common.utils import keystone as keystone_utils


class TripleOAction(actions.Action):

    def __init__(self):
        super(TripleOAction, self).__init__()

    def get_object_client(self, context):
        obj_ep = keystone_utils.get_endpoint_for_project(context, 'swift')

        kwargs = {
            'preauthurl': obj_ep.url % {'tenant_id': context.project_id},
            'preauthtoken': context.auth_token,
            'retries': 10,
            'starting_backoff': 3,
            'max_backoff': 120
        }

        return swift_client.Connection(**kwargs)

    def get_baremetal_client(self, context):
        ironic_endpoint = keystone_utils.get_endpoint_for_project(
            context, 'ironic')

        # FIXME(lucasagomes): Use ironicclient.get_client() instead
        # of ironicclient.Client(). Client() might cause errors since
        # it doesn't verify the provided arguments, get_client() is the
        # prefered way
        return ironicclient.Client(
            ironic_endpoint.url,
            token=context.auth_token,
            region_name=ironic_endpoint.region,
            os_ironic_api_version='1.33',
            # FIXME(lucasagomes):Paramtetize max_retries and
            # max_interval. At the moment since we are dealing with
            # a critical bug (#1612622) let's just hardcode the times
            # here since the right fix does involve multiple projects
            # (tripleo-ci and python-tripleoclient beyong tripleo-common)
            max_retries=12,
            retry_interval=5,
        )

    def get_baremetal_introspection_client(self, context):
        bmi_endpoint = keystone_utils.get_endpoint_for_project(
            context, 'ironic-inspector')

        return ironic_inspector_client.ClientV1(
            api_version='1.2',
            inspector_url=bmi_endpoint.url,
            region_name=bmi_endpoint.region,
            auth_token=context.auth_token
        )

    def get_image_client(self, context):
        glance_endpoint = keystone_utils.get_endpoint_for_project(
            context, 'glance')
        return glanceclient.Client(
            glance_endpoint.url,
            token=context.auth_token,
            region_name=glance_endpoint.region
        )

    def get_orchestration_client(self, context):
        heat_endpoint = keystone_utils.get_endpoint_for_project(
            context, 'heat')

        endpoint_url = keystone_utils.format_url(
            heat_endpoint.url,
            {'tenant_id': context.project_id}
        )

        return heatclient.Client(
            endpoint_url,
            region_name=heat_endpoint.region,
            token=context.auth_token,
            username=context.user_name
        )

    def get_messaging_client(self, context):
        zaqar_endpoint = keystone_utils.get_endpoint_for_project(
            context, service_type='messaging')
        keystone_endpoint = keystone_utils.get_endpoint_for_project(
            context, 'keystone')

        opts = {
            'os_auth_token': context.auth_token,
            'os_auth_url': keystone_endpoint.url,
            'os_project_id': context.project_id,
            'insecure': context.insecure,
        }
        auth_opts = {'backend': 'keystone', 'options': opts}
        conf = {'auth_opts': auth_opts}

        return zaqarclient.Client(zaqar_endpoint.url, conf=conf)

    def get_workflow_client(self, context):
        mistral_endpoint = keystone_utils.get_endpoint_for_project(
            context, 'mistral')

        mc = mistral_client.client(auth_token=context.auth_token,
                                   mistral_url=mistral_endpoint.url)

        return mc

    def get_compute_client(self, context):
        keystone_endpoint = keystone_utils.get_endpoint_for_project(
            context, 'keystone')
        nova_endpoint = keystone_utils.get_endpoint_for_project(
            context, 'nova')

        client = nova_client(
            2,
            username=None,
            api_key=None,
            service_type='compute',
            auth_token=context.auth_token,
            tenant_id=context.project_id,
            region_name=keystone_endpoint.region,
            auth_url=keystone_endpoint.url,
            insecure=context.insecure
        )

        client.client.management_url = keystone_utils.format_url(
            nova_endpoint.url,
            {'tenant_id': context.project_id}
        )

        return client

    def _cache_key(self, plan_name, key_name):
        return "__cache_{}_{}".format(plan_name, key_name)

    def cache_get(self, context, plan_name, key):
        """Retrieves the stored objects

        Returns None if there are any issues or no objects found

        """

        swift_client = self.get_object_client(context)
        try:
            headers, body = swift_client.get_object(
                constants.TRIPLEO_CACHE_CONTAINER,
                self._cache_key(plan_name, key)
            )
            result = json.loads(zlib.decompress(body).decode())
            return result
        except swiftexceptions.ClientException:
            # cache does not exist, ignore
            pass
        except ValueError:
            # the stored json is invalid. Deleting
            self.cache_delete(context, plan_name, key)
        return

    def cache_set(self, context, plan_name, key, contents):
        """Stores an object

        Allows the storage of jsonable objects except for None
        Storing None equals to a cache delete.

        """

        swift_client = self.get_object_client(context)
        if contents is None:
            self.cache_delete(context, plan_name, key)
            return

        try:
            swift_client.head_container(constants.TRIPLEO_CACHE_CONTAINER)
        except swiftexceptions.ClientException:
            swift_client.put_container(constants.TRIPLEO_CACHE_CONTAINER)

        swift_client.put_object(
            constants.TRIPLEO_CACHE_CONTAINER,
            self._cache_key(plan_name, key),
            zlib.compress(json.dumps(contents).encode()))

    def cache_delete(self, context, plan_name, key):
        swift_client = self.get_object_client(context)
        try:
            swift_client.delete_object(
                constants.TRIPLEO_CACHE_CONTAINER,
                self._cache_key(plan_name, key)
            )
        except swiftexceptions.ClientException:
            # cache or container does not exist. Ignore
            pass
