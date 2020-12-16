# Copyright 2015 Red Hat, Inc.
# All Rights Reserved.
#
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
import logging
import sys

import six
from six import reraise as raise_

from tripleo_common.i18n import _

_FATAL_EXCEPTION_FORMAT_ERRORS = False

LOG = logging.getLogger(__name__)


@six.python_2_unicode_compatible
class TripleoCommonException(Exception):
    """Base Tripleo-Common Exception.

    To correctly use this class, inherit from it and define a 'msg_fmt'
    property. That msg_fmt will get printf'd with the keyword arguments
    provided to the constructor.
    """
    message = _("An unknown exception occurred.")

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.msg_fmt = self.message

        try:
            self.message = self.msg_fmt % kwargs
        except KeyError:
            exc_info = sys.exc_info()
            # kwargs doesn't match a variable in the message
            # log the issue and the kwargs
            LOG.exception('Exception in string format operation')
            for name, value in kwargs.items():
                LOG.error("%(name)s: %(value)s",
                          {'name': name, 'value': value})  # noqa

            if _FATAL_EXCEPTION_FORMAT_ERRORS:
                raise_(exc_info[0], exc_info[1], exc_info[2])

    def __str__(self):
        return self.message

    def __deepcopy__(self, memo):
        return self.__class__(**self.kwargs)


class StackInUseError(TripleoCommonException):
    msg_fmt = _("Cannot delete a plan that has an associated stack.")


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


class RootDeviceDetectionError(Exception):
    """Failed to detect the root device"""


class DeriveParamsError(Exception):
    """Error while performing a derive parameters operation"""


class NotFound(Exception):
    """Resource not found"""


class RoleMetadataError(Exception):
    """Role metadata is invalid"""


class UnauthorizedException(Exception):
    """Authorization failed"""


class GroupOsApplyConfigException(Exception):
    """group:os-apply-config not supported with config-download"""

    def __init__(self, deployment_name):
        self.deployment_name = deployment_name
        message = (
            "Deployment %s with group:os-apply-config not supported with "
            "config-download." % self.deployment_name)
        super(GroupOsApplyConfigException, self).__init__(message)
