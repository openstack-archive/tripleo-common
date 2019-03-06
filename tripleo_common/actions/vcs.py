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
import glob
import logging
import shutil
import tempfile

import six

from mistral_lib import actions
from tripleo_common.utils.safe_import import Repo


LOG = logging.getLogger(__name__)


class GitCloneAction(actions.Action):
    """Clones a remote git repository

    :param container: name of the container associated with the plan
    :param url: url of git repository
    :return: returns local path of cloned git repository
    """

    def __init__(self, container, url):
        super(GitCloneAction, self).__init__()
        self.container = container
        self.url = url

    def _checkout_reference(self, repo, ref):
        return repo.git.checkout(repo.refs[ref])

    def run(self, context):
        # make a temp directory to contain the repo
        local_dir_path = tempfile.mkdtemp(
            suffix="_%s_import" % self.container)
        url_bits = self.url.rsplit('@')
        err_msg = None
        try:
            # create a bare repo
            repo = Repo.clone_from(url_bits[0], local_dir_path)
        except Exception:
            err_msg = ("Error cloning remote repository: %s " % url_bits[0])
            LOG.exception(err_msg)
            return actions.Result(error=err_msg)

        # if a tag value was given, checkout that tag
        if len(url_bits) > 1:
            try:
                self._checkout_reference(repo, url_bits[-1])
            except IndexError:
                err_msg = ("Error finding %s reference "
                           "from remote repository" % url_bits[-1])
                LOG.exception(err_msg)
            except Exception:
                err_msg = ("Error checking out %s reference from remote "
                           "repository %s" % (url_bits[-1], url_bits[0]))
                LOG.exception(err_msg)

        if err_msg:
            return actions.Result(error=err_msg)

        return local_dir_path


class GitCleanupAction(actions.Action):
    """Removes temporary files associated with GitCloneAction operations

    :param container: name of the container associated with the plan
    :return: None if successful.  Returns error on failure to delete
    associated temporary files
    """
    def __init__(self, container):
        self.container = container

    def run(self, context):
        try:
            temp_dir = tempfile.gettempdir()
            target_path = '%s/*_%s_import' % (temp_dir, self.container)
            path = glob.glob(target_path)[0]
            shutil.rmtree(path)
        except IndexError as idx_err:
            LOG.exception("Directory not found: %s" % target_path)
            return actions.Result(error=six.text_type(idx_err))
        except OSError as os_err:
            LOG.exception("Error removing directory: %s" % target_path)
            return actions.Result(error=six.text_type(os_err))
