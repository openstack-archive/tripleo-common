# Copyright (c) 2013 Mirantis Inc.
# Copyright (c) 2017 Red Hat, Inc.
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

from keystoneclient import service_catalog as ks_service_catalog
from keystoneclient.v3 import client as ks_client
from keystoneclient.v3 import endpoints as ks_endpoints
import six

from tripleo_common import exception


def client(ctx):
    auth_url = ctx.auth_uri

    cl = ks_client.Client(
        user_id=ctx.user_id,
        token=ctx.auth_token,
        tenant_id=ctx.project_id,
        auth_url=auth_url
    )

    cl.management_url = auth_url

    return cl


def get_endpoint_for_project(ctx, service_name=None, service_type=None,
                             region_name=None):
    if service_name is None and service_type is None:
        raise ValueError(
            "Either 'service_name' or 'service_type' must be provided."
        )

    service_catalog = obtain_service_catalog(ctx)

    # When region_name is not passed, first get from context as region_name
    # could be passed to rest api in http header ('X-Region-Name'). Otherwise,
    # just get region from mistral configuration.
    region = (region_name or ctx.region_name)

    service_endpoints = service_catalog.get_endpoints(
        service_name=service_name,
        service_type=service_type,
        region_name=region
    )

    endpoint = None
    os_actions_endpoint_type = 'public'

    for endpoints in six.itervalues(service_endpoints):
        for ep in endpoints:
            # is V3 interface?
            if 'interface' in ep:
                interface_type = ep['interface']
                if os_actions_endpoint_type in interface_type:
                    endpoint = ks_endpoints.Endpoint(
                        None,
                        ep,
                        loaded=True
                    )
                    break
            # is V2 interface?
            if 'publicURL' in ep:
                endpoint_data = {
                    'url': ep['publicURL'],
                    'region': ep['region']
                }
                endpoint = ks_endpoints.Endpoint(
                    None,
                    endpoint_data,
                    loaded=True
                )
                break

    if not endpoint:
        raise RuntimeError(
            "No endpoints found [service_name=%s, service_type=%s,"
            " region_name=%s]"
            % (service_name, service_type, region)
        )
    else:
        return endpoint


def obtain_service_catalog(ctx):
    token = ctx.auth_token

    response = ctx.service_catalog

    # Target service catalog may not be passed via API.
    if not response and ctx.is_target:
        response = client().tokens.get_token_data(
            token,
            include_catalog=True
        )['token']

    if not response:
        raise exception.UnauthorizedException()

    service_catalog = ks_service_catalog.ServiceCatalog.factory(response)

    return service_catalog


def format_url(url_template, values):
    # Since we can't use keystone module, we can do similar thing:
    # see https://github.com/openstack/keystone/blob/master/keystone/
    # catalog/core.py#L42-L60
    return url_template.replace('$(', '%(') % values
