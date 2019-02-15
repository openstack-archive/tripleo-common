# Copyright (c) 2019 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utilities to handle processes."""

import logging
import os

from oslo_concurrency import processutils

LOG = logging.getLogger(__name__)


def execute(*cmd, **kwargs):
    """Convenience wrapper around oslo's execute() method.

    Executes and logs results from a system command. See docs for
    oslo_concurrency.processutils.execute for usage.

    :param \*cmd: positional arguments to pass to processutils.execute()
    :param use_standard_locale: keyword-only argument. True | False.
                                Defaults to False. If set to True,
                                execute command with standard locale
                                added to environment variables.
    :param log_stdout: keyword-only argument. True | False. Defaults
                       to True. If set to True, logs the output.
    :param \*\*kwargs: keyword arguments to pass to processutils.execute()
    :returns: (stdout, stderr) from process execution
    :raises: UnknownArgumentError on receiving unknown arguments
    :raises: ProcessExecutionError
    :raises: OSError
    """

    use_standard_locale = kwargs.pop('use_standard_locale', False)
    if use_standard_locale:
        env = kwargs.pop('env_variables', os.environ.copy())
        env['LC_ALL'] = 'C'
        kwargs['env_variables'] = env
    log_stdout = kwargs.pop('log_stdout', True)
    result = processutils.execute(*cmd, **kwargs)
    LOG.debug('Execution completed, command line is "%s"',
              ' '.join(map(str, cmd)))
    if log_stdout:
        LOG.debug('Command stdout is: "%s"', result[0])
    LOG.debug('Command stderr is: "%s"', result[1])
    return result
