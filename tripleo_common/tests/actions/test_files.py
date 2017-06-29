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
