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
from ironicclient.v1 import client as ironicclient
from mistral.actions import base
from mistral import context
from mistral.utils.openstack import keystone as keystone_utils
from mistralclient.api import client as mistral_client
from novaclient.client import Client as nova_client
from swiftclient import client as swift_client


class TripleOAction(base.Action):

    def __init__(self):
        super(TripleOAction, self).__init__()

    def get_object_client(self):
        ctx = context.ctx()
        obj_ep = keystone_utils.get_endpoint_for_project('swift')

        kwargs = {
            'preauthurl': obj_ep.url % {'tenant_id': ctx.project_id},
            'preauthtoken': ctx.auth_token,
            'retries': 10,
            'starting_backoff': 3,
            'max_backoff': 120
        }

        return swift_client.Connection(**kwargs)

    def get_baremetal_client(self):
        ctx = context.ctx()

        ironic_endpoint = keystone_utils.get_endpoint_for_project('ironic')

        # FIXME(lucasagomes): Use ironicclient.get_client() instead
        # of ironicclient.Client(). Client() might cause errors since
        # it doesn't verify the provided arguments, get_client() is the
        # prefered way
        return ironicclient.Client(
            ironic_endpoint.url,
            token=ctx.auth_token,
            region_name=ironic_endpoint.region,
            os_ironic_api_version='1.15',
            # FIXME(lucasagomes):Paramtetize max_retries and
            # max_interval. At the moment since we are dealing with
            # a critical bug (#1612622) let's just hardcode the times
            # here since the right fix does involve multiple projects
            # (tripleo-ci and python-tripleoclient beyong tripleo-common)
            max_retries=12,
            retry_interval=5,
        )

    def get_baremetal_introspection_client(self):
        ctx = context.ctx()

        bmi_endpoint = keystone_utils.get_endpoint_for_project(
            'ironic-inspector')

        return ironic_inspector_client.ClientV1(
            api_version='1.2',
            inspector_url=bmi_endpoint.url,
            region_name=bmi_endpoint.region,
            auth_token=ctx.auth_token
        )

    def get_image_client(self):
        ctx = context.ctx()

        glance_endpoint = keystone_utils.get_endpoint_for_project('glance')
        return glanceclient.Client(
            glance_endpoint.url,
            token=ctx.auth_token,
            region_name=glance_endpoint.region
        )

    def get_orchestration_client(self):
        ctx = context.ctx()
        heat_endpoint = keystone_utils.get_endpoint_for_project('heat')

        endpoint_url = keystone_utils.format_url(
            heat_endpoint.url,
            {'tenant_id': ctx.project_id}
        )

        return heatclient.Client(
            endpoint_url,
            region_name=heat_endpoint.region,
            token=ctx.auth_token,
            username=ctx.user_name
        )

    def get_workflow_client(self):
        ctx = context.ctx()
        mistral_endpoint = keystone_utils.get_endpoint_for_project('mistral')

        mc = mistral_client.client(auth_token=ctx.auth_token,
                                   mistral_url=mistral_endpoint.url)

        return mc

    def get_compute_client(self):
        ctx = context.ctx()
        keystone_endpoint = keystone_utils.get_endpoint_for_project('keystone')
        nova_endpoint = keystone_utils.get_endpoint_for_project('nova')

        client = nova_client(
            2,
            username=None,
            api_key=None,
            service_type='compute',
            auth_token=ctx.auth_token,
            tenant_id=ctx.project_id,
            region_name=keystone_endpoint.region,
            auth_url=keystone_endpoint.url,
            insecure=ctx.insecure
        )

        client.client.management_url = keystone_utils.format_url(
            nova_endpoint.url,
            {'tenant_id': ctx.project_id}
        )

        return client
