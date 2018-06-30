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
import logging
import os
import re
import shutil
import six
import subprocess
import tempfile
import time

from mistral_lib import actions
from mistral_lib.actions import base

from tripleo_common.actions import base as tripleobase
from tripleo_common.utils import swift as swiftutils

LOG = logging.getLogger(__name__)


class GetFreeSpace(base.Action):
    """Get the Undercloud free space for the backup.

       The default path to check will be /var/tmp and the
       default minimum size will be 10240 MB (10GB).
    """

    def __init__(self, min_space=10240, temp_dir="/var/tmp/"):
        self.min_space = min_space
        self.temp_dir = temp_dir

    def run(self, context):
        temp_path = self.temp_dir
        min_space = self.min_space
        while not os.path.isdir(temp_path):
            head, tail = os.path.split(temp_path)
            temp_path = head
        available_space = (
            (os.statvfs(temp_path).f_frsize * os.statvfs(temp_path).f_bavail) /
            (1024 * 1024))
        if (available_space < min_space):
            msg = "There is not enough space, avail. - %s MB" \
                  % str(int(available_space))
            return actions.Result(error={'msg': msg})
        else:
            msg = "There is enough space, avail. - %s MB" \
                  % str(int(available_space))
            return actions.Result(data={'msg': msg})


class CreateBackupDir(base.Action):
    """Creates the Backup temporary directory.

       We will run the backup locally, so we need to create a temporary
       directory.  The directory created will match the regular expression
       ^/var/tmp/undercloud-backup-[A-Za-z0-9_]{6}$
    """

    def __init__(self):
        pass

    def run(self, context):
        try:
            _path = tempfile.mkdtemp(prefix='undercloud-backup-',
                                     dir='/var/tmp/')
            return actions.Result(data={"path": _path})
        except Exception as msg:
            return actions.Result(error={"msg": six.text_type(msg)})


class CreateDatabaseBackup(base.Action):
    """Creates a database full backup.

       This action will run the DB dump using a single transaction and storing
       the result in a given folder.
    """

    def __init__(self, path, dbuser, dbpassword):
        self.path = path
        self.dbuser = dbuser
        self.dbpassword = dbpassword
        self.backup_name = os.path.join(self.path,
                                        'all-databases-' +
                                        time.strftime("%Y%m%d%H%M%S") +
                                        '.sql.gz')

    def run(self, context):
        pid_file = tempfile.gettempdir() + os.sep + "mysqldump.pid"
        if os.path.exists(pid_file):
            msg = 'Another Backup process is running'
            return actions.Result(error={"msg": six.text_type(msg)})
        lockfile = open(pid_file, 'w')
        lockfile.write("%s\n" % os.getpid())
        lockfile.close

        # Backup all databases with nice and ionice just not to create
        # a huge load on undercloud. Output will be redirected to mysqldump
        # variable and will be gzipped.
        script = """
        #!/bin/bash
        nice -n 19 ionice -c2 -n7 \
            mysqldump -u%s -p%s --opt --all-databases | gzip > %s
        """ % (self.dbuser, self.dbpassword, self.backup_name)

        proc_failed = False

        try:
            subprocess.check_call(script, shell=True)
        except subprocess.CalledProcessError:
            proc_failed = True
            msg = 'Database dump failed. Deleting temporary directory'
            os.remove(self.backup_name)
        else:
            msg = 'Database dump created succesfully'
        finally:
            os.remove(pid_file)

        if proc_failed:
            return actions.Result(error={'msg': six.text_type(msg)})
        else:
            return actions.Result(data={'msg': six.text_type(msg)})


class CreateFileSystemBackup(base.Action):
    """Creates a File System backup.

       This action will run a filesystem backup based on an array of resources
       to be backed up.  This method gets the sources paths and the destination
       folder as parameters.
    """

    def __init__(self, sources_path, path):
        self.sources_path = sources_path
        self.path = path
        self.outfile = os.path.join(self.path,
                                    'filesystem-' +
                                    time.strftime("%Y%m%d%H%M%S") +
                                    '.tar')

    def run(self, context):

        backup_sources = self.sources_path.split(',')
        separated_string = ' '.join(backup_sources)

        script = """
        #!/bin/bash
        sudo tar --xattrs --ignore-failed-read -C / -cf %s %s
        sudo chown mistral. %s
        """ % (self.outfile, separated_string, self.outfile)

        proc_failed = False
        if self.sources_path:
            try:
                subprocess.check_call(script, shell=True)
            except subprocess.CalledProcessError:
                proc_failed = True
                msg = 'File system backup failed'
                os.remove(self.outfile)
            else:
                msg = ('File system backup created succesfully at: %s'
                       % self.outfile)
        else:
            msg = 'File system backup has no files to backup'

        if proc_failed:
            # Delete failed backup here
            return actions.Result(error={'msg': six.text_type(msg)})
        else:
            return actions.Result(data={'msg': msg})


class UploadUndercloudBackupToSwift(tripleobase.TripleOAction):
    """Push the Undercloud backup to a swift container.

       This action will push the files in the temporary folder to the swift
       container storing the Undercloud backups as uncompressed tarball file.
       The backup will be stored 1 day (86400 s)
    """

    def __init__(self,
                 backup_path,
                 container='undercloud-backups',
                 expire=86400):
        self.backup_path = backup_path
        self.container = container
        self.expire = expire
        self.tarball_name = 'UC-backup-%s.tar' % time.strftime(
                            "%Y%m%d%H%M%S")

    def run(self, context):
        try:
            LOG.info('Uploading backup to swift')
            swift_service = self.get_object_service(context)
            # Create tarball without gzip and store it 24h
            swiftutils.create_and_upload_tarball(
                swift_service, self.backup_path, self.container,
                self.tarball_name, '-cf', self.expire)

            msg = 'Backup uploaded to undercloud-backups succesfully'
            return actions.Result(data={'msg': msg})
        except Exception as msg:
            return actions.Result(error={'msg': six.text_type(msg)})


class RemoveTempDir(base.Action):
    """Removes temporary directory on localhost by path.

    The path must match the regular expression
    ^/var/tmp/undercloud-backup-[A-Za-z0-9_]+$
    """

    def __init__(self, path):
        self.path = path

    def run(self, context):
        # regex from tempfile's _RandomNameSequence characters
        _regex = '^/var/tmp/undercloud-backup-[A-Za-z0-9_]{6}$'
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
