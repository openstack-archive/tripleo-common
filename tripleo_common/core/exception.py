# Copyright 2015 Red Hat, Inc.
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
import six
from six import reraise as raise_
import sys

from tripleo_common.core.i18n import _
from tripleo_common.core.i18n import _LE

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

        try:
            self.message = self.msg_fmt % kwargs
        except KeyError:
            exc_info = sys.exc_info()
            # kwargs doesn't match a variable in the message
            # log the issue and the kwargs
            LOG.exception(_LE('Exception in string format operation'))
            for name, value in six.iteritems(kwargs):
                LOG.error(_LE("%(name)s: %(value)s"),
                          {'name': name, 'value': value})  # noqa

            if _FATAL_EXCEPTION_FORMAT_ERRORS:
                raise_(exc_info[0], exc_info[1], exc_info[2])

    def __str__(self):
        return self.message

    def __deepcopy__(self, memo):
        return self.__class__(**self.kwargs)


class StackInUseError(TripleoCommonException):
    msg_fmt = _("Cannot delete a plan that has an associated stack.")


class PlanDoesNotExistError(TripleoCommonException):
    msg_fmt = _("A plan with the name %(name)s does not exist.")


class FileDoesNotExistError(TripleoCommonException):
    msg_fmt = _("A file with the name %(name)s does not exist.")


class PlanAlreadyExistsError(TripleoCommonException):
    msg_fmt = _("A plan with the name %(name)s already exists.")


class TooManyRootTemplatesError(TripleoCommonException):
    msg_fmt = _("There can only be up to one root template in a given plan.")


class HeatValidationFailedError(TripleoCommonException):
    msg_fmt = _("The plan failed to validate via the Heat service. %(msg)s")


class MappingFileNotFoundError(TripleoCommonException):
    msg_fmt = _("The capabilities_map.yaml file was not found in the root"
                " of the plan.")


class TooManyCapabilitiesMapFilesError(TripleoCommonException):
    msg_fmt = _("There cannot be more than one root template in a given plan.")
