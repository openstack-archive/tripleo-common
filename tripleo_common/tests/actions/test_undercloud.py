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
import mock

from tripleo_common.actions import undercloud
from tripleo_common.tests import base


class GetFreeSpaceTest(base.TestCase):
    def setUp(self):
        super(GetFreeSpaceTest, self).setUp()
        self.temp_dir = "/var/tmp"

    @mock.patch("os.path.isdir")
    @mock.patch("os.statvfs")
    def test_run_false(self, mock_statvfs, mock_isdir):
        mock_isdir.return_value = True
        mock_statvfs.return_value = mock.MagicMock(
            spec_set=['f_frsize', 'f_bavail'],
            f_frsize=4096, f_bavail=1024)
        action = undercloud.GetFreeSpace()
        action_result = action.run(context={})
        mock_isdir.assert_called()
        mock_statvfs.assert_called()
        self.assertEqual("There is not enough space, avail. - 4 MB",
                         action_result.error['msg'])

    @mock.patch("os.path.isdir")
    @mock.patch("os.statvfs")
    def test_run_true(self, mock_statvfs, mock_isdir):
        mock_isdir.return_value = True
        mock_statvfs.return_value = mock.MagicMock(
            spec_set=['f_frsize', 'f_bavail'],
            f_frsize=4096, f_bavail=10240000)
        action = undercloud.GetFreeSpace()
        action_result = action.run(context={})
        mock_isdir.assert_called()
        mock_statvfs.assert_called()
        self.assertEqual("There is enough space, avail. - 40000 MB",
                         action_result.data['msg'])


class RemoveTempDirTest(base.TestCase):

    def setUp(self):
        super(RemoveTempDirTest, self).setUp()
        self.path = "/var/tmp/undercloud-backup-dG6hr_"

    @mock.patch("shutil.rmtree")
    def test_sucess_remove_temp_dir(self, mock_rmtree):
        mock_rmtree.return_value = None  # rmtree has no return value
        action = undercloud.RemoveTempDir(self.path)
        action_result = action.run(context={})
        mock_rmtree.assert_called()
        self.assertFalse(action_result.cancel)
        self.assertIsNone(action_result.error)
        self.assertEqual('Deleted directory /var/tmp/undercloud-backup-dG6hr_',
                         action_result.data['msg'])


class CreateDatabaseBackupTest(base.TestCase):

    def setUp(self):
        super(CreateDatabaseBackupTest, self).setUp()
        self.dbback = undercloud.CreateDatabaseBackup(
            '/var/tmp/undercloud-backup-dG6hr_',
            'root', 'dbpassword')

    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('subprocess.check_call')
    def test_create_database_backup(
            self, mock_check_call, mock_get_object_client):
        self.dbback.logger = mock.Mock()
        self.dbback.run(mock_get_object_client)
        assert_string = ('\n        #!/bin/bash\n        '
                         'nice -n 19 ionice -c2 -n7             '
                         'mysqldump -uroot -pdbpassword --opt '
                         '--all-databases | gzip > ' +
                         self.dbback.backup_name +
                         '\n        ')
        mock_check_call.assert_called_once_with(assert_string, shell=True)


class CreateFileSystemBackupTest(base.TestCase):

    def setUp(self):
        super(CreateFileSystemBackupTest, self).setUp()
        self.fsback = undercloud.CreateFileSystemBackup(
            '/home/stack/,/etc/hosts',
            '/var/tmp/undercloud-backup-ef9b_H')
        self.fsemptyback = undercloud.CreateFileSystemBackup(
            '',
            '/var/tmp/undercloud-backup-ef9b_H')

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('subprocess.check_call')
    def test_create_file_system_backup(
            self,
            mock_check_call,
            mock_get_object_client):
        self.fsback.logger = mock.Mock()
        self.fsback.run(mock_get_object_client)
        assert_string = ('\n        #!/bin/bash\n        '
                         'sudo tar --xattrs --ignore-failed-read -C / '
                         '-cf ' +
                         self.fsback.outfile +
                         ' /home/stack/ /etc/hosts\n        '
                         'sudo chown mistral. ' +
                         self.fsback.outfile +
                         '\n        ')
        mock_check_call.assert_called_once_with(assert_string, shell=True)

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    @mock.patch('subprocess.check_call')
    def test_create_empty_file_system_backup(
            self,
            mock_check_call,
            mock_get_object_client):
        self.fsemptyback.logger = mock.Mock()
        self.fsemptyback.run(mock_get_object_client)
        mock_check_call.assert_not_called()


class CreateBackupDirTest(base.TestCase):

    def setUp(self):
        super(CreateBackupDirTest, self).setUp()
        self.temp_dir = '/var/tmp/undercloud-backup-XXXXXX'

    @mock.patch('tempfile.mkdtemp')
    def test_run(self, mock_mkdtemp):
        mock_mkdtemp.return_value = self.temp_dir
        action = undercloud.CreateBackupDir()
        action_result = action.run(context={})
        mock_mkdtemp.assert_called()
        self.assertEqual(self.temp_dir,
                         action_result.data['path'])


class UploadUndercloudBackupToSwiftTest(base.TestCase):

    def setUp(self,):
        super(UploadUndercloudBackupToSwiftTest, self).setUp()
        self.container = 'undercloud-backups'
        self.backup_path = '/var/tmp/undercloud-backups-sdf_45'
        self.tarball_name = 'UC-backup-20180112124502.tar'
        self.swift = mock.MagicMock()
        swift_patcher = mock.patch(
            'tripleo_common.actions.base.TripleOAction.get_object_client',
            return_value=self.swift)
        swift_patcher.start()
        self.addCleanup(swift_patcher.stop)
        self.ctx = mock.MagicMock()

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_service')
    @mock.patch('tripleo_common.utils.tarball.create_tarball')
    def test_upload_to_swift_success(self,
                                     mock_create_tarball,
                                     mock_get_obj_service):

        self.swift.head_object.return_value = {
            'content-length': 1
        }
        self.swift.get_container.return_value = (
            {}, []
        )

        swift_service = mock.MagicMock()
        swift_service.delete.return_value = ([
            {'success': True},
        ])
        mock_get_obj_service.return_value = swift_service

        action = undercloud.UploadUndercloudBackupToSwift(
            self.backup_path, self.container)
        action.run(self.ctx)

        swift_service.upload.has_calls()

        options = {'use_slo': True,
                   'changed': None,
                   'meta': [],
                   'fail_fast': True,
                   'leave_segments': False,
                   'header': ['X-Delete-After: 86400'],
                   'skip_identical': False,
                   'segment_size': 1048576000,
                   'segment_container': None,
                   'dir_marker': False}

        swift_service.upload.assert_called_once_with(
            self.container,
            mock.ANY,
            options=options
            )

        mock_create_tarball.assert_called_once()
