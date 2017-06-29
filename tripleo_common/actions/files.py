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
import tempfile


from mistral_lib import actions
from mistral_lib.actions import base


class FileExists(base.Action):
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


class MakeTempDir(base.Action):
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


class RemoveTempDir(base.Action):
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
