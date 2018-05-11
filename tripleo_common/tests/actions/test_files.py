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

from tripleo_common.actions import files
from tripleo_common.tests import base


class FileExistsTest(base.TestCase):

    def setUp(self):
        super(FileExistsTest, self).setUp()
        self.path = '/etc/issue'

    @mock.patch("os.path.exists")
    def test_file_exists(self, mock_exists):
        mock_exists.return_value = True
        action = files.FileExists(self.path)
        action_result = action.run(context={})
        self.assertFalse(action_result.cancel)
        self.assertIsNone(action_result.error)
        self.assertEqual('Found file /etc/issue',
                         action_result.data['msg'])


class MakeTempDirTest(base.TestCase):

    def setUp(self):
        super(MakeTempDirTest, self).setUp()

    @mock.patch("tempfile.mkdtemp")
    def test_make_temp_dir(self, mock_mkdtemp):
        mock_mkdtemp.return_value = "/tmp/file-mistral-actionxFLfYz"
        action = files.MakeTempDir()
        action_result = action.run(context={})
        self.assertFalse(action_result.cancel)
        self.assertIsNone(action_result.error)
        self.assertEqual('/tmp/file-mistral-actionxFLfYz',
                         action_result.data['path'])


class RemoveTempDirTest(base.TestCase):

    def setUp(self):
        super(RemoveTempDirTest, self).setUp()
        self.path = "/tmp/file-mistral-actionxFLfYz"

    @mock.patch("shutil.rmtree")
    def test_sucess_remove_temp_dir(self, mock_rmtree):
        mock_rmtree.return_value = None  # rmtree has no return value
        action = files.RemoveTempDir(self.path)
        action_result = action.run(context={})
        self.assertFalse(action_result.cancel)
        self.assertIsNone(action_result.error)
        self.assertEqual('Deleted directory /tmp/file-mistral-actionxFLfYz',
                         action_result.data['msg'])


class SaveTempDirToSwiftTest(base.TestCase):
    def setUp(self):
        super(SaveTempDirToSwiftTest, self).setUp()
        self.path = "/tmp/file-mistral-actionxFLfYz"
        self.container = "my_container"
        self.tarball = "foo.tar.gz"

    @mock.patch("tripleo_common.utils.swift.create_and_upload_tarball")
    @mock.patch("tripleo_common.actions.base.TripleOAction.get_object_service")
    @mock.patch("tripleo_common.actions.base.TripleOAction.get_object_client")
    def test_save_temp_dir_to_swift(self, mock_get_object_client,
                                    mock_get_object_service,
                                    mock_create_and_upload_tarball):
        # Setup context, swift, swift_service, get_container, create_upload
        mock_ctx = mock.MagicMock()

        swift = mock.MagicMock(url="http://test.com")
        mock_get_object_client.return_value = swift

        swift_service = mock.MagicMock()
        mock_get_object_service.return_value = swift_service

        def return_container_files(*args):
            return ('headers', [])

        swift.get_container = mock.MagicMock(
            side_effect=return_container_files)
        mock_get_object_client.return_value = swift

        mock_create_and_upload_tarball.return_value = mock.MagicMock(
            swift_service, self.path, self.container, self.tarball)

        # Test
        action = files.SaveTempDirToSwift(self.path, self.container)
        result = action.run(mock_ctx)

        # Verify
        self.assertFalse(result.cancel)
        self.assertIsNone(result.error)
        msg = "Saved tarball of directory: %s in Swift container: %s" \
              % (self.path, self.container)
        self.assertEqual(msg, result.data['msg'])


class RestoreTempDirFromSwiftTest(base.TestCase):
    def setUp(self):
        super(RestoreTempDirFromSwiftTest, self).setUp()
        self.path = "/tmp/file-mistral-actionxFLfYz"
        self.container = "my_container"
        self.tarball = "foo.tar.gz"

    @mock.patch("os.listdir")
    @mock.patch("tripleo_common.utils.tarball.extract_tarball")
    @mock.patch("tripleo_common.utils.swift.download_container")
    @mock.patch("tripleo_common.actions.base.TripleOAction.get_object_client")
    def test_restore_temp_dir_from_swift(self, mock_get_object_client,
                                         mock_download_container,
                                         mock_extract_tarball, mock_listdir):
        # Setup context, swift, listdir, tarball
        mock_ctx = mock.MagicMock()

        swift = mock.MagicMock(url="http://test.com")
        mock_get_object_client.return_value = swift

        mock_download_container.return_value = mock.MagicMock(
            swift, self.container, self.path)
        mock_extract_tarball.return_value = mock.MagicMock(
            self.path, self.tarball)
        mock_listdir.return_value = [self.tarball]

        # Test
        action = files.RestoreTempDirFromSwift(self.path, self.container)
        result = action.run(mock_ctx)

        # Verify
        self.assertFalse(result.cancel)
        self.assertIsNone(result.error)
        msg = "Swift container: %s has been extracted to directory: %s" \
              % (self.container, self.path)
        self.assertEqual(msg, result.data['msg'])
