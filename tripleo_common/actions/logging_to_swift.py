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
import json
import logging
import shutil
import tempfile
import time

from mistral_lib import actions
from oslo_concurrency import processutils
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import base
from tripleo_common import constants
from tripleo_common.utils import swift as swiftutils
from tripleo_common.utils import time_functions as timeutils

LOG = logging.getLogger(__name__)


class FormatMessagesAction(actions.Action):
    """Format messages as logs

    Given a list of Zaqar messages from the TripleO UI, return a log-formatted
    string
    """
    def __init__(self, messages):
        super(FormatMessagesAction, self).__init__()
        self.messages = messages

    def run(self, context):
        lines = []

        for zaqar_message in self.messages:
            log_object = zaqar_message.get('body')

            if not log_object:
                continue

            body = log_object.get('message', '')
            level = log_object.get('level', 'info')
            timestamp = log_object.get('timestamp', time.time() * 1000)

            if isinstance(body, (dict, list,)):
                body = json.dumps(body)

            lines.append(
                '{date} {level} {body}'.format(
                    date=timeutils.epoch_to_formatted_date(timestamp),
                    level=level,
                    body=body
                )
            )

        return '\n'.join(lines)


class PublishUILogToSwiftAction(base.TripleOAction):
    """Publish logs from UI to Swift"""

    def __init__(self, logging_data, logging_container):
        super(PublishUILogToSwiftAction, self).__init__()
        self.logging_data = logging_data
        self.logging_container = logging_container

    def _rotate(self, swift):
        """Optimistic log rotation

        Failure to sucessfully complete log rotation doesn't cause the
        entire action to fail
        """
        try:
            headers = swift.head_object(self.logging_container,
                                        constants.TRIPLEO_UI_LOG_FILENAME)
            content_length = int(headers['content-length'])
            if content_length < constants.TRIPLEO_UI_LOG_FILE_SIZE:
                LOG.debug("Log file hasn't reached a full size so it doesn't"
                          " need to be rotated.")
                return
        except swiftexceptions.ClientException:
            LOG.debug("Couldn't get existing log file, skip log rotation.")
            return

        try:
            files = swift.get_container(self.logging_container)[1]
        except swiftexceptions.ClientException:
            LOG.warn("Logging container doesn't exist, skip log rotation.")
            return

        largest_existing_suffix = 0

        for f in files:
            try:
                suffix = int(f['name'].split('.')[-1])
                if suffix > largest_existing_suffix:
                    largest_existing_suffix = suffix
            except ValueError:
                continue

        next_suffix = largest_existing_suffix + 1
        next_filename = '{}.{}'.format(
            constants.TRIPLEO_UI_LOG_FILENAME, next_suffix)
        try:
            data = swift.get_object(self.logging_container,
                                    constants.TRIPLEO_UI_LOG_FILENAME)[1]
            swift.put_object(self.logging_container, next_filename, data)
            swift.delete_object(self.logging_container,
                                constants.TRIPLEO_UI_LOG_FILENAME)
        except swiftexceptions.ClientException as err:
            msg = "Log rotation failed: %s" % err
            LOG.warn(msg)

    def run(self, context):
        swift = self.get_object_client(context)
        swiftutils.get_or_create_container(swift, self.logging_container)
        self._rotate(swift)

        try:
            old_contents = swift.get_object(
                self.logging_container,
                constants.TRIPLEO_UI_LOG_FILENAME)[1]
            new_contents = old_contents + '\n' + self.logging_data
        except swiftexceptions.ClientException:
            LOG.debug(
                "There is no existing logging data, starting a new file.")
            new_contents = self.logging_data

        try:
            swift.put_object(self.logging_container,
                             constants.TRIPLEO_UI_LOG_FILENAME,
                             new_contents)
        except swiftexceptions.ClientException as err:
            msg = "Failed to publish logs: %s" % err
            return actions.Result(error=msg)


class PrepareLogDownloadAction(base.TripleOAction):
    """Publish all GUI logs to a temporary URL"""

    def __init__(self, logging_container, downloads_container, delete_after):
        super(PrepareLogDownloadAction, self).__init__()
        self.logging_container = logging_container
        self.downloads_container = downloads_container
        self.delete_after = delete_after

    def run(self, context):
        swift = self.get_object_client(context)
        swift_service = self.get_object_service(context)

        tmp_dir = tempfile.mkdtemp()
        tarball_name = 'logs-%s.tar.gz' % timeutils.timestamp()

        try:
            swiftutils.download_container(
                swift, self.logging_container, tmp_dir)
            swiftutils.create_and_upload_tarball(
                swift_service, tmp_dir, self.downloads_container,
                tarball_name, delete_after=self.delete_after)
        except swiftexceptions.ClientException as err:
            msg = "Error attempting an operation on container: %s" % err
            return actions.Result(error=msg)
        except (OSError, IOError) as err:
            msg = "Error while writing file: %s" % err
            return actions.Result(error=msg)
        except processutils.ProcessExecutionError as err:
            msg = "Error while creating a tarball: %s" % err
            return actions.Result(error=msg)
        except Exception as err:
            msg = "Error exporting logs: %s" % err
            return actions.Result(error=msg)
        finally:
            shutil.rmtree(tmp_dir)

        return tarball_name
