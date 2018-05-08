# Copyright 2018 Red Hat, Inc.
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

# Ansible has another callback plugin just called "json.py", which overrides
# a normal import of "import json", so use absolute imports
from __future__ import absolute_import
import json
import os

from ansible.plugins.callback import CallbackBase

from tripleo_common import constants


DOCUMENTATION = '''
    callback: json_error
    short_description: Write errors in JSON format to a log file
    description:
        - This callback writes errors in JSON format to a log file
    type: aggregate
    options:
      output_dir:
        name: json-error log file
        default: ansible-error.json
        description: Log file where to write errors in JSON format.
        env:
          - name: JSON_ERROR_LOG_FILE
'''


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.5
    CALLBACK_TYPE = 'aggregate'
    CALLBACK_NAME = 'json-error'

    def __init__(self, display=None):
        super(CallbackModule, self).__init__(display)
        self.errors = {}
        self.log_file = os.getenv(
            'JSON_ERROR_LOG_FILE',
            constants.ANSIBLE_ERRORS_FILE)

    def v2_playbook_on_stats(self, stats):
        with open(self.log_file, 'w') as f:
            f.write(json.dumps(self.errors))

    def v2_runner_on_failed(self, result, ignore_errors=False):
        if not ignore_errors:
            host_errors = self.errors.setdefault(result._host.name, [])
            host_errors.append((result.task_name, result._result))
