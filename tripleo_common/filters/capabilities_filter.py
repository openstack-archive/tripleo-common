# Copyright 2016 Red Hat, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from nova.scheduler import filters
from oslo_log import log as logging


LOG = logging.getLogger(__name__)


class TripleOCapabilitiesFilter(filters.BaseHostFilter):
    """Filter hosts based on capabilities in boot request

    The standard Nova ComputeCapabilitiesFilter does not respect capabilities
    requested in the scheduler_hints field, so we need a custom one in order
    to be able to do predictable placement of nodes.
    """

    # list of hosts doesn't change within a request
    run_filter_once_per_request = True

    def host_passes(self, host_state, spec_obj):
        host_node = host_state.stats.get('node')
        instance_node = spec_obj.scheduler_hints.get('capabilities:node')
        # The instance didn't request a specific node
        if not instance_node:
            LOG.debug('No specific node requested')
            return True
        if host_node == instance_node[0]:
            LOG.debug('Node tagged %s matches requested node %s', host_node,
                      instance_node[0])
            return True
        else:
            LOG.debug('Node tagged %s does not match requested node %s',
                      host_node, instance_node[0])
            return False
