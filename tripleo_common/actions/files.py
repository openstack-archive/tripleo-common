# Copyright 2017 Red Hat, Inc.
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
import os
import re
import shutil
import six
import sys
import tempfile

from mistral_lib import actions
from oslo_concurrency import processutils
from swiftclient import exceptions as swiftexceptions
from tripleo_common.actions import base
from tripleo_common.utils import swift as swiftutils
from tripleo_common.utils import tarball
from tripleo_common.utils import time_functions as timeutils


class FileExists(base.TripleOAction):
    """Verifies if a path exists on the localhost (undercloud)"""
    def __init__(self, path):
        self.path = path

    def run(self, context):
        if (isinstance(self.path, six.string_types) and
                os.path.exists(self.path)):
            msg = "Found file %s" % self.path
            return actions.Result(data={"msg": msg})
        else:
            msg = "File %s not found" % self.path
            return actions.Result(error={"msg": msg})


class MakeTempDir(base.TripleOAction):
    """Creates temporary directory on localhost

    The directory created will match the regular expression
    ^/tmp/file-mistral-action[A-Za-z0-9_]{6}$
    """

    def __init__(self):
        pass

    def run(self, context):
        try:
            _path = tempfile.mkdtemp(dir='/tmp/',
                                     prefix='file-mistral-action')
            return actions.Result(data={"path": _path})
        except Exception as msg:
            return actions.Result(error={"msg": six.text_type(msg)})


class RemoveTempDir(base.TripleOAction):
    """Removes temporary directory on localhost by path.

    The path must match the regular expression
    ^/tmp/file-mistral-action[A-Za-z0-9_]{6}$
    """

    def __init__(self, path):
        self.path = path

    def run(self, context):
        # regex from tempfile's _RandomNameSequence characters
        _regex = '^/tmp/file-mistral-action[A-Za-z0-9_]{6}$'
        if (not isinstance(self.path, six.string_types) or
                not re.match(_regex, self.path)):
            msg = "Path does not match %s" % _regex
            return actions.Result(error={"msg": msg})
        try:
            shutil.rmtree(self.path)
            msg = "Deleted directory %s" % self.path
            return actions.Result(data={"msg": msg})
        except Exception as msg:
            return actions.Result(error={"msg": six.text_type(msg)})


class SaveTempDirToSwift(base.TripleOAction):
    """Save temporary directory, identified by path, to Swift container

    The path must match the regular expression
    ^/tmp/file-mistral-action[A-Za-z0-9_]{6}$

    The Swift container must exist

    Contents from path will be packaged in a tarball before upload

    Older tarball(s) will be replaced with the one that is uploaded
    """

    def __init__(self, path, container):
        super(SaveTempDirToSwift, self).__init__()
        self.path = path
        self.container = container

    def run(self, context):
        swift = self.get_object_client(context)
        swift_service = self.get_object_service(context)
        tarball_name = 'temporary_dir-%s.tar.gz' \
                       % timeutils.timestamp()
        # regex from tempfile's _RandomNameSequence characters
        _regex = '^/tmp/file-mistral-action[A-Za-z0-9_]{6}$'
        if (not isinstance(self.path, six.string_types) or
                not re.match(_regex, self.path)):
            msg = "Path does not match %s" % _regex
            return actions.Result(error={"msg": msg})
        try:
            headers, objects = swift.get_container(self.container)
            for o in objects:
                swift.delete_object(self.container, o['name'])
            swiftutils.create_and_upload_tarball(
                swift_service, self.path, self.container,
                tarball_name, delete_after=sys.maxsize)
        except swiftexceptions.ClientException as err:
            msg = "Error attempting an operation on container: %s" % err
            return actions.Result(error={"msg": six.text_type(msg)})
        except (OSError, IOError) as err:
            msg = "Error while writing file: %s" % err
            return actions.Result(error={"msg": six.text_type(msg)})
        except processutils.ProcessExecutionError as err:
            msg = "Error while creating a tarball: %s" % err
            return actions.Result(error={"msg": six.text_type(msg)})
        except Exception as err:
            msg = "Error exporting logs: %s" % err
            return actions.Result(error={"msg": six.text_type(msg)})
        msg = "Saved tarball of directory: %s in Swift container: %s" % (
            self.path, self.container)
        return actions.Result(data={"msg": msg})


class RestoreTempDirFromSwift(base.TripleOAction):
    """Unpack tarball from Swift container into temporary directory at path

    The path must exist and match the regular expression
    ^/tmp/file-mistral-action[A-Za-z0-9_]{6}$

    Container should contain a single tarball object
    If container is empty, then no error is returned
    """

    def __init__(self, path, container):
        super(RestoreTempDirFromSwift, self).__init__()
        self.path = path
        self.container = container

    def run(self, context):
        swift = self.get_object_client(context)
        # regex from tempfile's _RandomNameSequence characters
        _regex = '^/tmp/file-mistral-action[A-Za-z0-9_]{6}$'
        if (not isinstance(self.path, six.string_types) or
                not re.match(_regex, self.path)):
            msg = "Path does not match %s" % _regex
            return actions.Result(error={"msg": msg})
        try:
            swiftutils.download_container(swift, self.container, self.path)
            filenames = os.listdir(self.path)
            if len(filenames) == 0:
                pass
            elif len(filenames) == 1:
                tarball.extract_tarball(self.path, filenames[0], remove=True)
            else:
                msg = "%d objects found in container: %s" \
                      % (len(filenames), self.container)
                msg += " but one object was expected."
                return actions.Result(error={"msg": six.text_type(msg)})
        except swiftexceptions.ClientException as err:
            msg = "Error attempting an operation on container: %s" % err
            return actions.Result(error={"msg": six.text_type(msg)})
        except (OSError, IOError) as err:
            msg = "Error while writing file: %s" % err
            return actions.Result(error={"msg": six.text_type(msg)})
        except processutils.ProcessExecutionError as err:
            msg = "Error while creating a tarball: %s" % err
            return actions.Result(error={"msg": six.text_type(msg)})
        except Exception as err:
            msg = "Error exporting logs: %s" % err
            return actions.Result(error={"msg": six.text_type(msg)})
        msg = "Swift container: %s has been extracted to directory: %s" % (
            self.container, self.path)
        return actions.Result(data={"msg": msg})
