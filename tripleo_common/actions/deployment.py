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
from cryptography.hazmat.backends import default_backend
from cryptography import x509
import json
import logging
import os
import time

from heatclient.common import deployment_utils
from heatclient import exc as heat_exc
from mistral_lib import actions
from oslo_concurrency import processutils
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common.actions import templates
from tripleo_common import constants
from tripleo_common.utils import overcloudrc
from tripleo_common.utils import plan as plan_utils

LOG = logging.getLogger(__name__)


class OrchestrationDeployAction(base.TripleOAction):

    def __init__(self, server_id, config, name, input_values=[],
                 action='CREATE', signal_transport='TEMP_URL_SIGNAL',
                 timeout=300, group='script'):
        super(OrchestrationDeployAction, self).__init__()
        self.server_id = server_id
        self.config = config
        self.input_values = input_values
        self.action = action
        self.name = name
        self.signal_transport = signal_transport
        self.timeout = timeout
        self.group = group

    def _extract_container_object_from_swift_url(self, swift_url):
        container_name = swift_url.split('/')[-2]
        object_name = swift_url.split('/')[-1].split('?')[0]
        return (container_name, object_name)

    def _build_sc_params(self, swift_url):
        source = {
            'config': self.config,
            'group': self.group,
        }
        return deployment_utils.build_derived_config_params(
            action=self.action,
            source=source,
            name=self.name,
            input_values=self.input_values,
            server_id=self.server_id,
            signal_transport=self.signal_transport,
            signal_id=swift_url
        )

    def _wait_for_data(self, container_name, object_name, context):
        body = None
        count_check = 0
        swift_client = self.get_object_client(context)
        while not body:
            headers, body = swift_client.get_object(
                container_name,
                object_name
            )
            count_check += 3
            if body or count_check > self.timeout:
                break
            time.sleep(3)

        return body

    def run(self, context):
        heat = self.get_orchestration_client(context)
        swift_client = self.get_object_client(context)

        swift_url = deployment_utils.create_temp_url(swift_client,
                                                     self.name,
                                                     self.timeout)
        container_name, object_name = \
            self._extract_container_object_from_swift_url(swift_url)

        params = self._build_sc_params(swift_url)
        config = heat.software_configs.create(**params)

        sd = heat.software_deployments.create(
            tenant_id='asdf',  # heatclient requires this
            config_id=config.id,
            server_id=self.server_id,
            action=self.action,
            status='IN_PROGRESS'
        )

        body = self._wait_for_data(container_name, object_name, context)

        # cleanup
        try:
            sd.delete()
            config.delete()
            swift_client.delete_object(container_name, object_name)
            swift_client.delete_container(container_name)
        except Exception as err:
            LOG.error("Error cleaning up heat deployment resources.", err)

        error = None
        if not body:
            body_json = {}
            error = "Timeout for heat deployment '%s'" % self.name
        else:
            body_json = json.loads(body)
            if body_json['deploy_status_code'] != 0:
                error = "Heat deployment failed for '%s'" % self.name

        if error:
            LOG.error(error)

        return actions.Result(data=body_json, error=error)


class DeployStackAction(templates.ProcessTemplatesAction):
    """Deploys a heat stack."""

    def __init__(self, timeout, container=constants.DEFAULT_CONTAINER_NAME,
                 skip_deploy_identifier=False):
        super(DeployStackAction, self).__init__(container)
        self.timeout_mins = timeout
        self.skip_deploy_identifier = skip_deploy_identifier

    def run(self, context):
        # check to see if the stack exists
        heat = self.get_orchestration_client(context)
        try:
            stack = heat.stacks.get(self.container)
        except heat_exc.HTTPNotFound:
            stack = None

        stack_is_new = stack is None

        # update StackAction, DeployIdentifier and UpdateIdentifier
        swift = self.get_object_client(context)

        parameters = dict()
        if not self.skip_deploy_identifier:
            parameters['DeployIdentifier'] = int(time.time())
        parameters['UpdateIdentifier'] = ''
        parameters['StackAction'] = 'CREATE' if stack_is_new else 'UPDATE'

        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        self.set_tls_parameters(parameters, env)
        try:
            plan_utils.update_in_env(swift, env, 'parameter_defaults',
                                     parameters)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error updating environment for plan %s: %s" % (
                self.container, err))
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        # process all plan files and create or update a stack
        processed_data = super(DeployStackAction, self).run(context)

        # If we receive a 'Result' instance it is because the parent action
        # had an error.
        if isinstance(processed_data, actions.Result):
            return processed_data

        stack_args = processed_data.copy()
        stack_args['timeout_mins'] = self.timeout_mins

        if stack_is_new:
            try:
                swift.copy_object(
                    "%s-swift-rings" % self.container, "swift-rings.tar.gz",
                    "%s-swift-rings/%s-%d" % (
                        self.container, "swift-rings.tar.gz", time.time()))
                swift.delete_object(
                    "%s-swift-rings" % self.container, "swift-rings.tar.gz")
            except swiftexceptions.ClientException:
                pass
            LOG.info("Perfoming Heat stack create")
            return heat.stacks.create(**stack_args)

        LOG.info("Performing Heat stack update")
        stack_args['existing'] = 'true'
        return heat.stacks.update(stack.id, **stack_args)

    def set_tls_parameters(self, parameters, env,
                           local_ca_path=constants.LOCAL_CACERT_PATH,
                           overcloud_cert_path=constants.OVERCLOUD_CERT_PATH,
                           overcloud_key_path=constants.OVERCLOUD_KEY_PATH):
        cacert_string = self._get_local_cacert(local_ca_path)
        if not cacert_string:
            return

        parameters['CAMap'] = self._get_updated_camap_entry(
            'undercloud-ca', cacert_string, self._get_camap(env))
        cert_path = overcloud_cert_path.format(container=self.container)
        key_path = overcloud_key_path.format(container=self.container)
        if self._deployment_needs_local_cert(env, cert_path, key_path):
            self._request_cert_if_necessary(env, cert_path, key_path)
            parameters['SSLCertificate'] = self._get_local_file(cert_path)
            parameters['SSLKey'] = self._get_local_file(key_path)

    def _get_local_cacert(self, local_ca_path):
        # Since the undercloud has TLS by default, we'll add the undercloud's
        # CA to be trusted by the overcloud.
        try:
            with open(local_ca_path, 'rb') as ca_file:
                return ca_file.read()
        except IOError:
            # If the file wasn't found it means that the undercloud's TLS
            # was explicitly disabled or another CA is being used. So we'll
            # let the user handle this.
            return None
        except Exception:
            raise

    def _get_local_file(self, path):
        with open(path, 'rb') as openfile:
            return openfile.read()

    def _get_camap(self, env):
        return env['parameter_defaults'].get('CAMap', {})

    def _get_overcloud_tls_certificate(self, env):
        cert_raw = env['parameter_defaults'].get('SSLCertificate', b'')
        if hasattr(cert_raw, 'encode'):
            return cert_raw.encode('ascii')
        else:
            return cert_raw

    def _get_updated_camap_entry(self, entry_name, cacert, orig_camap):
        ca_map_entry = {
            entry_name: {
                'content': cacert
            }
        }
        orig_camap.update(ca_map_entry)
        return orig_camap

    def _cert_is_from_local_issuer(self, cert):
        for attribute in cert.issuer:
            # '2.5.4.3' is the OID of the certificate issuer's CommonName or CN
            # 'Local Signing Authority' is the default CA name that certmonger
            # uses for the local CA
            if (attribute.oid.dotted_string == '2.5.4.3' and
                    attribute.value == 'Local Signing Authority'):
                return True
        return False

    def _deployment_needs_local_cert(self, env, cert_path, key_path):
        overcloud_cert_bytes = self._get_overcloud_tls_certificate(env)
        overcloud_certmonger = env['parameter_defaults'].get(
            'PublicSSLCertificateAutogenerated', False)
        enable_tls_flag = env['parameter_defaults'].get(
            'EnablePublicTLS', True)
        if overcloud_cert_bytes:
            overcloud_cert = x509.load_pem_x509_certificate(
                overcloud_cert_bytes, default_backend())
            if not self._cert_is_from_local_issuer(overcloud_cert):
                return False
        elif overcloud_certmonger or not enable_tls_flag:
            return False
        return True

    def _request_cert_if_necessary(self, env, cert_path, key_path):
        overcloud_fqdn = env['parameter_defaults'].get(
            'CloudName', 'overcloud.localdomain')
        if self._local_cert_request_present():
            # Even if certmonger is tracking the request, the user
            # might have deleted the cert file, so we resubmit the request.
            if not os.path.isfile(cert_path):
                self._request_local_cert(
                    overcloud_fqdn,
                    resubmit=True)
            if not os.path.isfile(key_path):
                raise RuntimeError(
                    "The key \"{0}\" is not present, you'll need to "
                    "recreate the certificate manually.".format(key_path))
        else:
            self._request_local_cert(overcloud_fqdn)

    def _request_local_cert(self, overcloud_fqdn, resubmit=False):
        action = 'request' if not resubmit else 'resubmit'
        return processutils.execute(
            '/usr/bin/sudo',
            '/usr/bin/tripleo-overcloud-cert',
            action,
            self.container,
            overcloud_fqdn)

    def _local_cert_request_present(self):
        try:
            processutils.execute(
                '/usr/bin/sudo',
                '/usr/bin/tripleo-overcloud-cert',
                'query',
                self.container)
            return True
        except processutils.ProcessExecutionError:
            return False


class OvercloudRcAction(base.TripleOAction):
    """Generate the overcloudrc and overcloudrc.v3 for a plan

    Given the name of a container, generate the overcloudrc files needed to
    access the overcloud via the CLI.

    no_proxy is optional and is a comma-separated string of hosts that
    shouldn't be proxied
    """

    def __init__(self, container, no_proxy=""):
        super(OvercloudRcAction, self).__init__()
        self.container = container
        self.no_proxy = no_proxy

    def run(self, context):
        orchestration_client = self.get_orchestration_client(context)
        swift = self.get_object_client(context)

        try:
            stack = orchestration_client.stacks.get(self.container)
        except heat_exc.HTTPNotFound:
            error = (
                "The Heat stack {} could not be found. Make sure you have "
                "deployed before calling this action.").format(self.container)
            return actions.Result(error=error)

        # We need to check parameter_defaults first for a user provided
        # password. If that doesn't exist, we then should look in the
        # automatically generated passwords.
        # TODO(d0ugal): Abstract this operation somewhere. We shouldn't need to
        # know about the structure of the environment to get a password.
        try:
            env = plan_utils.get_env(swift, self.container)
        except swiftexceptions.ClientException as err:
            err_msg = ("Error retrieving environment for plan %s: %s" % (
                self.container, err))
            LOG.error(err_msg)
            return actions.Result(error=err_msg)

        try:
            parameter_defaults = env['parameter_defaults']
            passwords = env['passwords']
            admin_pass = parameter_defaults.get('AdminPassword')
            if admin_pass is None:
                admin_pass = passwords['AdminPassword']
        except KeyError:
            error = ("Unable to find the AdminPassword in the plan "
                     "environment.")
            return actions.Result(error=error)

        return overcloudrc.create_overcloudrc(stack, self.no_proxy, admin_pass)
