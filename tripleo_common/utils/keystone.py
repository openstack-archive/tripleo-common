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

import six

from keystoneauth1.identity.generic import Token as IdentityToken
from keystoneauth1 import loading
from keystoneauth1 import session as ks_session
from keystoneauth1.token_endpoint import Token as SimpleToken
from keystoneclient import service_catalog as ks_service_catalog
from keystoneclient.v3 import client as ks_client
from keystoneclient.v3 import endpoints as ks_endpoints
from oslo_config import cfg

from tripleo_common import exception

CONF = cfg.CONF


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


def _determine_verify(ctx):
    if ctx.insecure:
        return False
    if ctx.auth_cacert:
        return ctx.auth_cacert
    return True


def get_session_and_auth(context, **kwargs):
    """Get session and auth parameters

    :param context: action context
    :return: dict to be used as kwargs for client serviceinitialization
    """

    if not context:
        raise AssertionError('context is mandatory')

    if context.trust_id:
        kwargs['project_name'] = None
        kwargs['project_domain_name'] = None
        kwargs['project_id'] = None
        kwargs['trust_id'] = context.trust_id
        kwargs.pop('service_name')

        auth = loading.load_auth_from_conf_options(
            CONF,
            'keystone_authtoken',
            **kwargs
        )
        session = loading.load_session_from_conf_options(
            CONF,
            'keystone',
            auth=auth
        )
    else:
        project_endpoint = get_endpoint_for_project(context, **kwargs)
        endpoint = format_url(
            project_endpoint.url,
            {
                'tenant_id': context.project_id,
                'project_id': context.project_id
            }
        )

        auth = SimpleToken(endpoint=endpoint, token=context.auth_token)

        auth_uri = context.auth_uri or CONF.keystone_authtoken.auth_uri
        ks_auth = SimpleToken(
            endpoint=auth_uri,
            token=context.auth_token
        )
        session = ks_session.Session(
            auth=ks_auth,
            verify=_determine_verify(context)
        )

    return {
        "session": session,
        "auth": auth
    }


# NOTE(dtantsur): get_session_and_auth returns a session tied to a specific
# service. This function returns a generic session. Eventually we should switch
# everything to using it and service-specific Adapter on top.
def get_session(context):
    """Get a generic session suitable for any service(s).

    :param context: action context
    :return: keystone `Session`
    """
    try:
        context = context.security
    except AttributeError:
        pass

    auth_uri = context.auth_uri or CONF.keystone_authtoken.auth_uri

    try:
        # TODO(dtantsur): a better way to detect the project domain?
        project_domain = context.service_catalog['project']['domain']['name']
    except KeyError:
        project_domain = CONF.keystone_authtoken.project_domain_name

    ks_auth = IdentityToken(auth_uri, token=context.auth_token,
                            # NOTE(dtantsur): project scope is required for V3
                            project_name=context.project_name,
                            project_domain_name=project_domain)
    sess = ks_session.Session(
        auth=ks_auth,
        verify=_determine_verify(context)
    )
    return sess


def _admin_client(trust_id=None):
    if CONF.keystone_authtoken.auth_type is None:
        auth_url = CONF.keystone_authtoken.auth_uri
        project_name = CONF.keystone_authtoken.admin_tenant_name

        # You can't use trust and project together

        if trust_id:
            project_name = None

        cl = ks_client.Client(
            username=CONF.keystone_authtoken.admin_user,
            password=CONF.keystone_authtoken.admin_password,
            project_name=project_name,
            auth_url=auth_url,
            trust_id=trust_id
        )

        cl.management_url = auth_url

        return cl

    kwargs = {}

    if trust_id:
        # Remove project_name and project_id, since we need a trust scoped
        # auth object
        kwargs['domain_id'] = None
        kwargs['domain_name'] = None
        kwargs['project_name'] = None
        kwargs['project_domain_name'] = None
        kwargs['project_id'] = None
        kwargs['trust_id'] = trust_id

    auth = loading.load_auth_from_conf_options(
        CONF,
        'keystone_authtoken',
        **kwargs
    )
    sess = loading.load_session_from_conf_options(
        CONF,
        'keystone',
        auth=auth
    )

    return ks_client.Client(session=sess)


def client_for_admin():
    return _admin_client()


def client_for_trusts(trust_id):
    return _admin_client(trust_id=trust_id)


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
    return endpoint


def obtain_service_catalog(ctx):
    token = ctx.auth_token

    if ctx.is_trust_scoped and is_token_trust_scoped(ctx, token):
        if ctx.trust_id is None:
            raise Exception(
                "'trust_id' must be provided in the admin context."
            )

        trust_client = client_for_trusts(ctx.trust_id)
        token_data = trust_client.tokens.get_token_data(
            token,
            include_catalog=True
        )
        response = token_data['token']
    else:
        response = ctx.service_catalog

        # Target service catalog may not be passed via API.
        # If we don't have the catalog yet, it should be requested.
        if not response:
            response = client(ctx).tokens.get_token_data(
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


def is_token_trust_scoped(ctx, auth_token):
    return 'OS-TRUST:trust' in client_for_admin().tokens.validate(auth_token)
