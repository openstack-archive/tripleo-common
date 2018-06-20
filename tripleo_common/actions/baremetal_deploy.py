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
from metalsmith import sources
from mistral_lib import actions
import six

from tripleo_common.actions import base
from tripleo_common.utils import keystone

LOG = logging.getLogger(__name__)


def _provisioner(context):
    session = keystone.get_session(context)
    return metalsmith.Provisioner(session=session)


_INSTANCES_INPUT_SCHEMA = {
    'type': 'array',
    'items': {
        'type': 'object',
        'properties': {
            'capabilities': {'type': 'object'},
            'hostname': {'type': 'string',
                         'minLength': 2,
                         'maxLength': 255},
            'image': {'type': 'string'},
            'image_checksum': {'type': 'string'},
            'image_kernel': {'type': 'string'},
            'image_ramdisk': {'type': 'string'},
            'name': {'type': 'string'},
            'nics': {'type': 'array',
                     'items': {'type': 'object',
                               'properties': {
                                   'network': {'type': 'string'},
                                   'port': {'type': 'string'},
                                   'fixed_ip': {'type': 'string'},
                               },
                               'additionalProperties': False}},
            'profile': {'type': 'string'},
            'resource_class': {'type': 'string'},
            'root_size_gb': {'type': 'integer', 'minimum': 4},
            'swap_size_mb': {'type': 'integer', 'minimum': 64},
            'traits': {'type': 'array',
                       'items': {'type': 'string'}},
        },
        'additionalProperties': False,
        # Host name is required, but defaults to name in _validate_instances
        'required': ['hostname'],
    }
}
"""JSON schema of the input for these actions."""


class CheckExistingInstancesAction(base.TripleOAction):
    """Detect which requested instances have already been provisioned."""

    def __init__(self, instances):
        super(CheckExistingInstancesAction, self).__init__()
        self.instances = instances

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
            try:
                instance = provisioner.show_instance(request['hostname'])
            # TODO(dtantsur): use openstacksdk exceptions when metalsmith
            # is bumped to 0.9.0.
            except Exception:
                not_found.append(request)
            else:
                found.append(instance.to_dict())

        if found:
            LOG.info('Found existing instances: %s',
                     ', '.join('%s (on node %s)' % (i['hostname'], i['uuid'])
                               for i in found))
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
                try:
                    node_id = node.id
                except AttributeError:
                    # TODO(dtantsur): transition from ironicclient to
                    # openstacksdk, remove when metalsmith is bumped to 0.9.0
                    node_id = node.uuid
                result.append({'node': node_id, 'instance': instance})
        except Exception as exc:
            LOG.exception('Provisioning failed, cleaning up')
            # Remove all reservations on failure
            try:
                _release_nodes(provisioner, nodes)
            except Exception:
                LOG.exception('Clean up failed, some nodes may still be '
                              'reserved by failed instances')
            return actions.Result(
                error="%s: %s" % (type(exc).__name__, exc)
            )

        return {'reservations': result}


class DeployNodeAction(base.TripleOAction):
    """Provision instance on a previously reserved node."""

    def __init__(self, instance, node, ssh_keys=None,
                 # For compatibility with deployment based on heat+nova
                 ssh_user_name='heat-admin',
                 default_image='overcloud-full',
                 default_network='ctlplane',
                 # 50 is the default for old flavors, subtracting 1G to account
                 # for partitioning and configdrive.
                 default_root_size=49):
        super(DeployNodeAction, self).__init__()
        self.instance = instance
        self.node = node
        self.config = metalsmith.InstanceConfig(ssh_keys=ssh_keys)
        self.config.add_user(ssh_user_name, admin=True, sudo=True)
        self.default_image = default_image
        self.default_network = default_network
        self.default_root_size = default_root_size

    def _get_image(self):
        # TODO(dtantsur): move this logic to metalsmith in 0.9.0
        image = self.instance.get('image', self.default_image)
        image_type = _link_type(image)
        if image_type == 'glance':
            return sources.GlanceImage(image)
        else:
            checksum = self.instance.get('image_checksum')
            if (checksum and image_type == 'http' and
                    _link_type(checksum) == 'http'):
                kwargs = {'checksum_url': checksum}
            else:
                kwargs = {'checksum': checksum}

            whole_disk_image = not (self.instance.get('image_kernel') or
                                    self.instance.get('image_ramdisk'))

            if whole_disk_image:
                if image_type == 'http':
                    return sources.HttpWholeDiskImage(image, **kwargs)
                else:
                    return sources.FileWholeDiskImage(image, **kwargs)
            else:
                if image_type == 'http':
                    return sources.HttpPartitionImage(
                        image,
                        kernel_url=self.instance.get('image_kernel'),
                        ramdisk_url=self.instance.get('image_ramdisk'),
                        **kwargs)
                else:
                    return sources.FilePartitionImage(
                        image,
                        kernel_location=self.instance.get('image_kernel'),
                        ramdisk_location=self.instance.get('image_ramdisk'),
                        **kwargs)

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
            instance = provisioner.provision_node(
                self.node,
                config=self.config,
                hostname=self.instance['hostname'],
                image=self._get_image(),
                nics=self.instance.get('nics',
                                       [{'network': self.default_network}]),
                root_size_gb=self.instance.get('root_size_gb',
                                               self.default_root_size),
                swap_size_mb=self.instance.get('swap_size_mb'),
            )
        except Exception as exc:
            LOG.exception('Provisioning of %s on node %s failed',
                          self.instance, self.node)
            try:
                _release_nodes(provisioner, [self.node])
            except Exception:
                LOG.exception('Clean up failed, node %s may still be '
                              'reserved by the failed instance', self.node)
            return actions.Result(
                error="%s: %s" % (type(exc).__name__, exc)
            )

        LOG.info('Started provisioning of %s on node %s',
                 self.instance, self.node)
        return instance.to_dict()


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
        instance = provisioner.wait_for_provisioning([self.instance['uuid']],
                                                     timeout=self.timeout)[0]
        LOG.info('Successfully provisioned instance %s',
                 self.instance['hostname'])
        return instance.to_dict()


class UndeployInstanceAction(base.TripleOAction):
    """Undeploy a previously deployed instance."""

    def __init__(self, instance, timeout=1800):
        super(UndeployInstanceAction, self).__init__()
        self.instance = instance
        self.timeout = timeout

    def run(self, context):
        provisioner = _provisioner(context)

        try:
            instance = provisioner.show_instance(self.instance)
        except Exception:
            LOG.warning('Cannot get instance %s, assuming already deleted',
                        self.instance)
            return

        LOG.debug('Unprovisioning instance %s', instance.hostname)
        provisioner.unprovision_node(instance.node, wait=self.timeout)
        LOG.info('Successfully unprovisioned %s', instance.hostname)


def _validate_instances(instances):
    for inst in instances:
        if inst.get('name') and not inst.get('hostname'):
            inst['hostname'] = inst['name']
    jsonschema.validate(instances, _INSTANCES_INPUT_SCHEMA)


def _release_nodes(provisioner, nodes):
    for node in nodes:
        LOG.debug('Removing reservation from node %s', node)
        try:
            provisioner.unprovision_node(node)
        except Exception:
            LOG.exception('Unable to release node %s, moving on', node)
        else:
            LOG.info('Removed reservation from node %s', node)


def _link_type(image):
    if image.startswith('http://') or image.startswith('https://'):
        return 'http'
    elif image.startswith('file://'):
        return 'file'
    else:
        return 'glance'
