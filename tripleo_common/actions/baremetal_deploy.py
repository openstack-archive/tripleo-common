# Copyright 2018 Red Hat, Inc.
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

import jsonschema
import metalsmith
from metalsmith import instance_config
from metalsmith import sources
from mistral_lib import actions
from openstack import exceptions as sdk_exc
import six

from tripleo_common.actions import base
from tripleo_common.utils import keystone

LOG = logging.getLogger(__name__)


def _provisioner(context):
    session = keystone.get_session(context)
    return metalsmith.Provisioner(session=session)


_IMAGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'href': {'type': 'string'},
        'checksum': {'type': 'string'},
        'kernel': {'type': 'string'},
        'ramdisk': {'type': 'string'},
    },
    'required': ['href'],
    'additionalProperties': False,
}

_NIC_SCHEMA = {
    'type': 'object',
    'properties': {
        'network': {'type': 'string'},
        'port': {'type': 'string'},
        'fixed_ip': {'type': 'string'},
        'subnet': {'type': 'string'},
    },
    'additionalProperties': False
}

_INSTANCE_SCHEMA = {
    'type': 'object',
    'properties': {
        'capabilities': {'type': 'object'},
        'hostname': {
            'type': 'string',
            'minLength': 2,
            'maxLength': 255
        },
        'image': _IMAGE_SCHEMA,
        'name': {'type': 'string'},
        'nics': {
            'type': 'array',
            'items': _NIC_SCHEMA
        },
        'profile': {'type': 'string'},
        'provisioned': {'type': 'boolean'},
        'resource_class': {'type': 'string'},
        'root_size_gb': {'type': 'integer', 'minimum': 4},
        'swap_size_mb': {'type': 'integer', 'minimum': 64},
        'traits': {
            'type': 'array',
            'items': {'type': 'string'}
        },
    },
    'additionalProperties': False,
}


_INSTANCES_SCHEMA = {
    'type': 'array',
    'items': _INSTANCE_SCHEMA
}
"""JSON schema of the instances list."""


_ROLES_INPUT_SCHEMA = {
    'type': 'array',
    'items': {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'hostname_format': {'type': 'string'},
            'count': {'type': 'integer', 'minimum': 0},
            'defaults': _INSTANCE_SCHEMA,
            'instances': _INSTANCES_SCHEMA,
        },
        'additionalProperties': False,
        'required': ['name'],
    }
}
"""JSON schema of the roles list."""


class CheckExistingInstancesAction(base.TripleOAction):
    """Detect which requested instances have already been provisioned."""

    def __init__(self, instances, default_resource_class='baremetal'):
        super(CheckExistingInstancesAction, self).__init__()
        self.instances = instances
        self.default_resource_class = default_resource_class

    def run(self, context):
        try:
            _validate_instances(self.instances)
        except Exception as exc:
            LOG.error('Failed to validate provided instances. %s', exc)
            return actions.Result(error=six.text_type(exc))

        provisioner = _provisioner(context)

        not_found = []
        found = []
        for request in self.instances:
            ident = request.get('name', request['hostname'])

            try:
                instance = provisioner.show_instance(ident)
            # TODO(dtantsur): replace Error with a specific exception
            except (sdk_exc.ResourceNotFound, metalsmith.exceptions.Error):
                not_found.append(request)
            except Exception as exc:
                message = ('Failed to request instance information for %s'
                           % ident)
                LOG.exception(message)
                return actions.Result(
                    error="%s. %s: %s" % (message, type(exc).__name__, exc)
                )
            else:
                # NOTE(dtantsur): metalsmith can match instances by node names,
                # provide a safeguard to avoid conflicts.
                if (instance.hostname and
                        instance.hostname != request['hostname']):
                    error = ("Requested hostname %s was not found, but the "
                             "deployed node %s has a matching name. Refusing "
                             "to proceed to avoid confusing results. Please "
                             "either rename the node or use a different "
                             "hostname") % (request['hostname'], instance.uuid)
                    return actions.Result(error=error)

                if (not instance.allocation
                        and instance.state == metalsmith.InstanceState.ACTIVE
                        and 'name' in request):
                    # Existing node is missing an allocation record,
                    # so create one without triggering allocation
                    LOG.debug('Reserving existing %s' % request['name'])
                    self.get_baremetal_client(context).allocation.create(
                        resource_class=request.get('resource_class') or
                        self.default_resource_class,
                        name=request['hostname'],
                        node=request['name']
                    )
                found.append(_instance_to_dict(provisioner.connection,
                                               instance))

        if found:
            LOG.info('Found existing instances: %s',
                     ', '.join(r['hostname'] for r in found))
        if not_found:
            LOG.info('Instance(s) %s do not exist',
                     ', '.join(r['hostname'] for r in not_found))

        return {
            'not_found': not_found,
            'instances': found
        }


class ReserveNodesAction(base.TripleOAction):
    """Reserve nodes for requested instances."""

    def __init__(self, instances, default_resource_class='baremetal'):
        super(ReserveNodesAction, self).__init__()
        self.instances = instances
        self.default_resource_class = default_resource_class

    def run(self, context):
        try:
            _validate_instances(self.instances)
        except Exception as exc:
            LOG.error('Failed to validate provided instances. %s', exc)
            return actions.Result(error=six.text_type(exc))

        provisioner = _provisioner(context)

        # TODO(dtantsur): looping over instances is not very optimal, change it
        # to metalsmith plan deployment API when it's available.
        result = []
        nodes = []
        try:
            for instance in self.instances:
                LOG.debug('Trying to reserve a node for instance %s', instance)
                if instance.get('name'):
                    # NOTE(dtantsur): metalsmith accepts list of nodes to pick
                    # from. We implement a simplest case when a user can pick a
                    # node by its name (actually, UUID will also work).
                    candidates = [instance['name']]
                else:
                    candidates = None

                if instance.get('profile'):
                    # TODO(dtantsur): change to traits?
                    instance.setdefault(
                        'capabilities', {})['profile'] = instance['profile']

                node = provisioner.reserve_node(
                    resource_class=instance.get('resource_class') or
                    self.default_resource_class,
                    capabilities=instance.get('capabilities'),
                    candidates=candidates,
                    traits=instance.get('traits'))
                LOG.info('Reserved node %s for instance %s', node, instance)
                nodes.append(node)
                result.append({'node': node.id, 'instance': instance})
        except Exception as exc:
            LOG.exception('Provisioning failed, cleaning up')
            # Remove all reservations on failure
            _release_nodes(provisioner, nodes)
            return actions.Result(
                error="%s: %s" % (type(exc).__name__, exc)
            )

        return {'reservations': result}


class DeployNodeAction(base.TripleOAction):
    """Provision instance on a previously reserved node."""

    def __init__(self, instance, node, ssh_keys=None,
                 # For compatibility with deployment based on heat+nova
                 ssh_user_name='heat-admin',
                 default_network='ctlplane',
                 # 50 is the default for old flavors, subtracting 1G to account
                 # for partitioning and configdrive.
                 default_root_size=49):
        super(DeployNodeAction, self).__init__()
        self.instance = instance
        self.node = node
        self.config = instance_config.CloudInitConfig(ssh_keys=ssh_keys)
        self.config.add_user(ssh_user_name, admin=True, sudo=True)
        self.default_network = default_network
        self.default_root_size = default_root_size

    def run(self, context):
        try:
            _validate_instances([self.instance])
        except Exception as exc:
            LOG.error('Failed to validate the request. %s', exc)
            return actions.Result(error=six.text_type(exc))

        provisioner = _provisioner(context)

        LOG.debug('Starting provisioning of %s on node %s',
                  self.instance, self.node)
        try:
            image = _get_source(self.instance)
            instance = provisioner.provision_node(
                self.node,
                config=self.config,
                hostname=self.instance['hostname'],
                image=image,
                nics=self.instance.get('nics',
                                       [{'network': self.default_network}]),
                root_size_gb=self.instance.get('root_size_gb',
                                               self.default_root_size),
                swap_size_mb=self.instance.get('swap_size_mb'),
            )
        except Exception as exc:
            LOG.exception('Provisioning of %s on node %s failed',
                          self.instance, self.node)
            _release_nodes(provisioner, [self.node])
            return actions.Result(
                error="%s: %s" % (type(exc).__name__, exc)
            )

        LOG.info('Started provisioning of %s on node %s',
                 self.instance, self.node)
        return _instance_to_dict(provisioner.connection, instance)


class WaitForDeploymentAction(base.TripleOAction):
    """Wait for the instance to be deployed."""

    def __init__(self, instance, timeout=3600):
        super(WaitForDeploymentAction, self).__init__()
        self.instance = instance
        self.timeout = timeout

    def run(self, context):
        provisioner = _provisioner(context)

        LOG.debug('Waiting for instance %s to provision',
                  self.instance['hostname'])
        try:
            instance = provisioner.wait_for_provisioning(
                [self.instance['uuid']], timeout=self.timeout)[0]
        except Exception as exc:
            LOG.exception('Provisioning of instance %s failed or timed out',
                          self.instance['hostname'])
            # Do not tear down, leave it up for the calling code to handle.
            return actions.Result(
                error="%s: %s" % (type(exc).__name__, exc)
            )
        LOG.info('Successfully provisioned instance %s',
                 self.instance['hostname'])
        return _instance_to_dict(provisioner.connection, instance)


class UndeployInstanceAction(base.TripleOAction):
    """Undeploy a previously deployed instance."""

    def __init__(self, instance, timeout=1800):
        super(UndeployInstanceAction, self).__init__()
        self.instance = instance
        self.timeout = timeout

    def run(self, context):
        provisioner = _provisioner(context)
        if isinstance(self.instance, dict):
            inst = self.instance['hostname']
        else:
            inst = self.instance
        try:
            instance = provisioner.show_instance(inst)
        except Exception:
            LOG.warning('Cannot get instance %s, assuming already deleted',
                        self.instance)
            return

        LOG.debug('Unprovisioning instance %s', instance.hostname)
        provisioner.unprovision_node(instance.node, wait=self.timeout)
        LOG.info('Successfully unprovisioned %s', instance.hostname)


class ExpandRolesAction(base.TripleOAction):
    """Convert a baremetal_deployment file to list of instances."""

    def __init__(self, roles, stackname='overcloud',
                 default_image='overcloud-full', provisioned=True):
        super(ExpandRolesAction, self).__init__()
        self.roles = roles
        self.stackname = stackname
        self.default_image = default_image
        self.provisioned = provisioned

    def run(self, context):
        for role in self.roles:
            role.setdefault('defaults', {})
            role['defaults'].setdefault(
                'image', {'href': self.default_image})
            for inst in role.get('instances', []):
                for k, v in role['defaults'].items():
                    inst.setdefault(k, v)

                # Set the default hostname now for duplicate hostname
                # detection during validation
                if 'hostname' not in inst and 'name' in inst:
                    inst['hostname'] = inst['name']

        try:
            _validate_roles(self.roles, stackname=self.stackname)
        except Exception as exc:
            LOG.error('Failed to validate the request. %s', exc)
            return actions.Result(error=six.text_type(exc))

        instances = []
        hostname_map = {}
        parameter_defaults = {'HostnameMap': hostname_map}
        for role in self.roles:
            name = role['name']
            hostname_format = _hostname_format(
                role.get('hostname_format'), name)
            count = role.get('count', 1)
            unprovisioned_indexes = []

            # build a map of all potential generated names
            # with the index number which generates the name
            potential_gen_names = {}
            for index in range(count + len(role.get('instances', []))):
                potential_gen_names[_build_hostname(
                    hostname_format, index, self.stackname)] = index

            # build a list of instances from the specified
            # instances list
            role_instances = []
            for instance in role.get('instances', []):
                inst = {}
                inst.update(instance)

                # create a hostname map entry now if the specified hostname
                # is a valid generated name
                if inst.get('hostname') in potential_gen_names:
                    hostname_map[inst['hostname']] = inst['hostname']

                role_instances.append(inst)

            # add generated instance entries until the desired count of
            # provisioned instances is reached
            while len([i for i in role_instances
                       if i.get('provisioned', True)]) < count:
                inst = {}
                inst.update(role['defaults'])
                role_instances.append(inst)

            # NOTE(dtantsur): our hostname format may differ from THT defaults,
            # so override it in the resulting environment
            parameter_defaults['%sHostnameFormat' % name] = (
                hostname_format)

            # ensure each instance has a unique non-empty hostname
            # and a hostname map entry. Also build a list of indexes
            # for unprovisioned instances
            index = 0
            for inst in role_instances:
                provisioned = inst.get('provisioned', True)
                gen_name = None
                hostname = inst.get('hostname')

                if hostname not in hostname_map:
                    while (not gen_name
                           or gen_name in hostname_map):
                        gen_name = _build_hostname(
                            hostname_format, index, self.stackname)
                        index += 1
                    inst.setdefault('hostname', gen_name)
                    hostname = inst.get('hostname')
                    hostname_map[gen_name] = inst['hostname']

                if not provisioned:
                    if gen_name:
                        unprovisioned_indexes.append(
                            potential_gen_names[gen_name])
                    elif hostname in potential_gen_names:
                        unprovisioned_indexes.append(
                            potential_gen_names[hostname])

            if unprovisioned_indexes:
                parameter_defaults['%sRemovalPolicies' % name] = [{
                    'resource_list': unprovisioned_indexes
                }]

            provisioned_count = 0
            for inst in role_instances:
                provisioned = inst.pop('provisioned', True)

                if provisioned:
                    provisioned_count += 1

                # Only add instances which match the desired provisioned state
                if provisioned == self.provisioned:
                    instances.append(inst)

            parameter_defaults['%sCount' % name] = (
                provisioned_count)

        try:
            _validate_instances(instances)
        except Exception as exc:
            LOG.error('Failed to validate the request. %s', exc)
            return actions.Result(error=six.text_type(exc))
        if self.provisioned:
            env = {'parameter_defaults': parameter_defaults}
        else:
            env = {}
        return {'instances': instances, 'environment': env}


class PopulateEnvironmentAction(base.TripleOAction):
    """Populate the resulting environment file.

    Fills in DeployedServerPortMap with the IP addresses of the nodes.
    """

    def __init__(self, environment, port_map, ctlplane_network='ctlplane'):
        super(PopulateEnvironmentAction, self).__init__()
        self.environment = environment
        self.port_map = port_map
        self.ctlplane_network = ctlplane_network

    def run(self, context):

        network_keys = (
            'mtu',
            'tags',
        )
        subnet_keys = (
            'cidr',
            'gateway_ip',
            'host_routes',
            'dns_nameservers',
        )
        resource_registry = self.environment.setdefault(
            'resource_registry', {})
        resource_registry.setdefault(
            'OS::TripleO::DeployedServer::ControlPlanePort',
            '/usr/share/openstack-tripleo-heat-templates'
            '/deployed-server/deployed-neutron-port.yaml')
        port_map = (self.environment.setdefault('parameter_defaults', {})
                    .setdefault('DeployedServerPortMap', {}))
        for hostname, nets in self.port_map.items():
            ctlplane_network = nets.get(self.ctlplane_network)
            if not ctlplane_network:
                LOG.warning('No ctlplane ports information for %s', hostname)
                continue
            fixed_ips = ctlplane_network.get('fixed_ips', [])
            network_all = ctlplane_network.get('network', {})
            network = {k: v for k, v in network_all.items()
                       if k in network_keys}
            subnets = []
            for subnet in ctlplane_network.get('subnets', []):
                subnets.append({k: v for k, v in subnet.items()
                                if k in subnet_keys})
            ctlplane = {
                'fixed_ips': fixed_ips,
                'network': network,
                'subnets': subnets
            }

            port_map['%s-%s' % (hostname, self.ctlplane_network)] = ctlplane

        return self.environment


def _validate_instances(instances):
    jsonschema.validate(instances, _INSTANCES_SCHEMA)
    hostnames = set()
    names = set()
    for inst in instances:
        # NOTE(dtantsur): validate image parameters
        _get_source(inst)

        if inst.get('hostname'):
            if inst['hostname'] in hostnames:
                raise ValueError('Hostname %s is used more than once' %
                                 inst['hostname'])
            hostnames.add(inst['hostname'])

        if inst.get('name'):
            if inst['name'] in names:
                raise ValueError('Node %s is requested more than once' %
                                 inst['name'])
            names.add(inst['name'])


def _validate_roles(roles, stackname='overcloud'):
    jsonschema.validate(roles, _ROLES_INPUT_SCHEMA)

    for item in roles:
        count = item.get('count', 1)
        instances = item.get('instances', [])
        instances = [i for i in instances if i.get('provisioned', True)]
        name = item.get('name')
        if len(instances) > count:
            raise ValueError(
                "%s: number of instance entries %s "
                "cannot be greater than count %s" %
                (name, len(instances), count)
            )

        defaults = item.get('defaults', {})
        if 'hostname' in defaults:
            raise ValueError("%s: cannot specify hostname in defaults"
                             % name)
        if 'name' in defaults:
            raise ValueError("%s: cannot specify name in defaults"
                             % name)
        if 'provisioned' in defaults:
            raise ValueError("%s: cannot specify provisioned in defaults"
                             % name)
        if 'instances' in item:
            _validate_instances(item['instances'])


def _release_nodes(provisioner, nodes):
    for node in nodes:
        LOG.debug('Removing reservation from node %s', node)
        try:
            provisioner.unprovision_node(node)
        except Exception:
            LOG.exception('Unable to release node %s, moving on', node)
        else:
            LOG.info('Removed reservation from node %s', node)


def _get_source(instance):
    image = instance.get('image', {})
    return sources.detect(image=image.get('href'),
                          kernel=image.get('kernel'),
                          ramdisk=image.get('ramdisk'),
                          checksum=image.get('checksum'))


def _instance_to_dict(connection, instance):
    """Convert an instance to a dict, adding ports information."""
    result = instance.to_dict()
    result['port_map'] = {}
    for nic in instance.nics():
        for ip in nic.fixed_ips:
            net_name = getattr(nic.network, 'name', None) or nic.network.id
            subnet = connection.network.get_subnet(ip['subnet_id'])
            net_info = result['port_map'].setdefault(
                net_name, {'network': nic.network.to_dict(),
                           'fixed_ips': [], 'subnets': []})
            net_info['fixed_ips'].append({'ip_address': ip['ip_address']})
            net_info['subnets'].append(subnet.to_dict())
    return result


def _hostname_format(hostname_format, role_name):
    if not hostname_format:
        hostname_format = '%stackname%-{}-%index%'.format(
            'novacompute' if role_name == 'Compute' else role_name.lower())
    return hostname_format


def _build_hostname(hostname_format, index, stack):
    gen_name = hostname_format.replace('%index%', str(index))
    gen_name = gen_name.replace('%stackname%', stack)
    return gen_name
