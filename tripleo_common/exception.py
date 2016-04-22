# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


class InvalidNode(ValueError):
    """Node data is invalid."""

    def __init__(self, message, node=None):
        message = 'Invalid node data: %s' % message
        self.node = node
        super(InvalidNode, self).__init__(message)


class Timeout(Exception):
    """An operation timed out"""

    def __init__(self, message):
        message = 'An operation timed out: %s' % message
        super(Timeout, self).__init__(message)


class StateTransitionFailed(Exception):
    """Ironic node state transition failed"""

    def __init__(self, node, target_state):
        self.node = node
        self.target_state = target_state
        message = (
            "Error transitioning Ironic node %(uuid)s to provision state "
            "%(state)s: %(error)s. Now in state %(actual)s." % {
                'uuid': node.uuid,
                'state': target_state,
                'error': node.last_error,
                'actual': node.provision_state
            }
        )
        super(StateTransitionFailed, self).__init__(message)
