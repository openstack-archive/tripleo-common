#   Copyright 2019 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#
# NOTE(mwhahaha): this class cannot be imported under Mistral because the
# multiprocessor.Manager inclusion breaks things due to the service launching
# to handle the multiprocess work.

import multiprocessing
from tripleo_common.utils.locks import base


class ProcessLock(base.BaseLock):
    # the manager cannot live in __init__
    _mgr = multiprocessing.Manager()
    _global_view = _mgr.dict()

    def __init__(self):
        # https://github.com/PyCQA/pylint/issues/3313
        # pylint: disable=no-member
        self._lock = self._mgr.Lock()
        self._objects = self._mgr.list()
        self._sessions = self._mgr.dict()
