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

from heatclient.v1 import client as heatclient
from mistral.actions import base
from mistral import context
from mistral.utils.openstack import keystone as keystone_utils
from mistralclient.api import client as mistral_client
from swiftclient import client as swift_client


LOG = logging.getLogger(__name__)


class TripleOAction(base.Action):

    def __init__(self):
        super(TripleOAction, self).__init__()

    def _get_object_client(self):
        ctx = context.ctx()
        obj_ep = keystone_utils.get_endpoint_for_project('swift')

        kwargs = {
            'preauthurl': obj_ep.url % {'tenant_id': ctx.project_id},
            'preauthtoken': ctx.auth_token
        }

        return swift_client.Connection(**kwargs)

    def _get_orchestration_client(self):
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

    def _get_workflow_client(self):
        ctx = context.ctx()
        mistral_endpoint = keystone_utils.get_endpoint_for_project('mistral')

        mc = mistral_client.client(auth_token=ctx.auth_token,
                                   mistral_url=mistral_endpoint.url)

        return mc
