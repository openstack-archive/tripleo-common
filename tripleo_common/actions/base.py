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

from glanceclient.v2 import client as glanceclient
from heatclient.v1 import client as heatclient
import ironic_inspector_client
from ironicclient import client as ironicclient
from keystoneauth1 import session as ks_session
from keystoneauth1.token_endpoint import Token
from mistral_lib import actions
from mistralclient.api import client as mistral_client
from novaclient.client import Client as nova_client
from swiftclient import client as swift_client
from swiftclient import service as swift_service
from zaqarclient.queues.v2 import client as zaqarclient

from tripleo_common.utils import keystone as keystone_utils


class TripleOAction(actions.Action):

    def __init__(self):
        super(TripleOAction, self).__init__()

    def get_session(self, context, service_name):
        session_and_auth = keystone_utils.get_session_and_auth(
            context,
            service_name=service_name
        )
        return session_and_auth['session']

    def get_object_client(self, context):
        security_ctx = context.security

        swift_endpoint = keystone_utils.get_endpoint_for_project(
            security_ctx,
            'swift'
        )

        kwargs = {
            'preauthurl': swift_endpoint.url % {
                'tenant_id': security_ctx.project_id
            },
            'session': self.get_session(security_ctx, 'swift'),
            'insecure': security_ctx.insecure,
            'retries': 10,
            'starting_backoff': 3,
            'max_backoff': 120
        }
        return swift_client.Connection(**kwargs)

    # This version returns the SwiftService API
    def get_object_service(self, context):
        swift_endpoint = keystone_utils.get_endpoint_for_project(
            context, 'swift')

        swift_opts = {
            'os_storage_url': swift_endpoint.url % {
                'tenant_id': context.project_id
            },
            'os_auth_token': context.auth_token,
            'os_region_name': swift_endpoint.region,
            'os_project_id': context.security.project_id,
        }

        return swift_service.SwiftService(options=swift_opts)

    def get_baremetal_client(self, context):
        security_ctx = context.security
        ironic_endpoint = keystone_utils.get_endpoint_for_project(
            security_ctx, 'ironic')

        return ironicclient.get_client(
            1,
            endpoint=ironic_endpoint.url,
            token=security_ctx.auth_token,
            region_name=ironic_endpoint.region,
            # 1.58 for allocations backfill
            os_ironic_api_version='1.58',
            # FIXME(lucasagomes):Paramtetize max_retries and
            # max_interval. At the moment since we are dealing with
            # a critical bug (#1612622) let's just hardcode the times
            # here since the right fix does involve multiple projects
            # (tripleo-ci and python-tripleoclient beyong tripleo-common)
            max_retries=12,
            retry_interval=5,
        )

    def get_baremetal_introspection_client(self, context):
        security_ctx = context.security
        bmi_endpoint = keystone_utils.get_endpoint_for_project(
            security_ctx, 'ironic-inspector')

        auth = Token(endpoint=bmi_endpoint.url, token=security_ctx.auth_token)

        return ironic_inspector_client.ClientV1(
            api_version='1.2',
            region_name=bmi_endpoint.region,
            session=ks_session.Session(auth)
        )

    def get_image_client(self, context):
        security_ctx = context.security
        try:
            glance_endpoint = keystone_utils.get_endpoint_for_project(
                security_ctx, 'glance')
        except Exception:
            return None

        return glanceclient.Client(
            glance_endpoint.url,
            token=security_ctx.auth_token,
            region_name=glance_endpoint.region
        )

    def get_orchestration_client(self, context):
        security_ctx = context.security
        heat_endpoint = keystone_utils.get_endpoint_for_project(
            security_ctx, 'heat')

        endpoint_url = keystone_utils.format_url(
            heat_endpoint.url,
            {'tenant_id': security_ctx.project_id}
        )

        return heatclient.Client(
            endpoint_url,
            region_name=heat_endpoint.region,
            token=security_ctx.auth_token,
            username=security_ctx.user_name
        )

    def get_messaging_client(self, context):
        zaqar_endpoint = keystone_utils.get_endpoint_for_project(
            context, service_type='messaging')

        auth_uri = context.security.auth_uri or \
            keystone_utils.CONF.keystone_authtoken.auth_uri

        opts = {
            'os_auth_token': context.security.auth_token,
            'os_auth_url': auth_uri,
            'os_project_id': context.security.project_id,
            'insecure': context.security.insecure,
        }
        auth_opts = {'backend': 'keystone', 'options': opts, }
        conf = {'auth_opts': auth_opts,
                'session': self.get_session(context, 'zaqar')}

        return zaqarclient.Client(zaqar_endpoint.url, conf=conf)

    def get_workflow_client(self, context):
        security_ctx = context.security
        mistral_endpoint = keystone_utils.get_endpoint_for_project(
            security_ctx, 'mistral')

        mc = mistral_client.client(auth_token=security_ctx.auth_token,
                                   mistral_url=mistral_endpoint.url)

        return mc

    def get_compute_client(self, context):
        security_ctx = context.security

        conf = keystone_utils.get_session_and_auth(
            security_ctx,
            service_type='compute'
        )

        return nova_client(2, **conf)
