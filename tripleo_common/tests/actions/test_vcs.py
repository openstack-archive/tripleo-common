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
import os
import shutil
import tempfile
import uuid

import git
from mistral_lib import actions

from tripleo_common.actions import vcs
from tripleo_common.tests import base


class GitCloneActionTest(base.TestCase):

    def setUp(self):
        super(GitCloneActionTest, self).setUp()

        self.temp_url = "/tmp/testdir"
        self.git_url = "https://github.com/openstack/tripleo-common.git"
        self.tag_ref = "some.test.ref"
        self.container = "overcloudtest"
        self.ctx = mock.MagicMock()

    @mock.patch('tempfile.mkdtemp')
    @mock.patch('git.Repo.clone_from')
    def test_run(self, mock_repo_clone, mock_mkdtemp):

        mock_mkdtemp.return_value = self.temp_url
        action = vcs.GitCloneAction(self.container, self.git_url)
        action.run(self.ctx)

        mock_mkdtemp.assert_called()
        mock_repo_clone.assert_called_with(self.git_url, self.temp_url)

    @mock.patch('tempfile.mkdtemp')
    @mock.patch('git.Repo.clone_from')
    def test_run_repo_failure(self, mock_repo_clone, mock_mkdtemp):

        mock_mkdtemp.return_value = self.temp_url
        mock_repo_clone.side_effect = git.exc.GitCommandError
        action = vcs.GitCloneAction(self.container, self.git_url)
        result = action.run(self.ctx)

        expected = actions.Result(
            error="Error cloning remote repository: %s " % self.git_url
        )

        mock_mkdtemp.assert_called()
        mock_repo_clone.assert_called_with(self.git_url, self.temp_url)
        self.assertEqual(result, expected)

    @mock.patch('tempfile.mkdtemp')
    @mock.patch('git.Repo.clone_from')
    @mock.patch(
        'tripleo_common.actions.vcs.GitCloneAction._checkout_reference')
    def test_run_ref_not_found(self, mock_checkout, mock_repo_clone,
                               mock_mkdtemp):

        mock_mkdtemp.return_value = self.temp_url
        mock_checkout.side_effect = IndexError
        action = vcs.GitCloneAction(
            self.container,
            "{url}@{tag}".format(url=self.git_url, tag=self.tag_ref)
        )
        result = action.run(self.ctx)

        err_msg = ("Error finding %s reference from remote repository" %
                   self.tag_ref)

        expected = actions.Result(error=err_msg)

        self.assertEqual(result, expected, "Error messages don't match.")

        mock_mkdtemp.assert_called()
        mock_repo_clone.assert_called_with(self.git_url, self.temp_url)

    @mock.patch('tempfile.mkdtemp')
    @mock.patch('git.Repo.clone_from')
    @mock.patch(
        'tripleo_common.actions.vcs.GitCloneAction._checkout_reference')
    def test_run_ref_checkout_error(self, mock_checkout, mock_repo_clone,
                                    mock_mkdtemp):

        mock_mkdtemp.return_value = self.temp_url
        mock_checkout.side_effect = git.cmd.GitCommandError
        action = vcs.GitCloneAction(
            self.container,
            "{url}@{tag}".format(url=self.git_url, tag=self.tag_ref)
        )
        result = action.run(self.ctx)

        err_msg = ("Error checking out %s reference from remote "
                   "repository %s" % (self.tag_ref, self.git_url))

        expected = actions.Result(error=err_msg)

        self.assertEqual(result, expected, "Error messages don't match.")

        mock_mkdtemp.assert_called()
        mock_repo_clone.assert_called_with(self.git_url, self.temp_url)


class GitCleanupActionTest(base.TestCase):

    def setUp(self):
        super(GitCleanupActionTest, self).setUp()
        self.container = "overcloud"
        self.temp_test_dir = tempfile.mkdtemp(
            suffix="_%s_import" % self.container)
        self.ctx = mock.MagicMock()

    def tearDown(self):
        super(GitCleanupActionTest, self).tearDown()
        if os.path.exists(self.temp_test_dir):
            shutil.rmtree(self.temp_test_dir)

    def test_run(self):
        action = vcs.GitCleanupAction(self.container)
        action.run(self.ctx)
        self.assertFalse(os.path.exists(self.temp_test_dir))

    def test_run_with_error(self):
        action = vcs.GitCleanupAction(str(uuid.uuid4()))
        result = action.run(self.ctx)
        self.assertIn("list index", str(result.error))
