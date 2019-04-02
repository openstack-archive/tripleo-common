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
"""Unit tests for image.builder.buildah"""

import copy
import mock

from tripleo_common.image.builder.buildah import BuildahBuilder as bb
from tripleo_common.tests import base
from tripleo_common.utils import process


BUILDAH_CMD_BASE = ['sudo', 'buildah']
DEPS = {"base"}
WORK_DIR = '/tmp/kolla'


class TestBuildahBuilder(base.TestCase):

    @mock.patch.object(process, 'execute', autospec=True)
    def test_build(self, mock_process):
        args = copy.copy(BUILDAH_CMD_BASE)
        dest = '127.0.0.1:8787/master/fedora-binary-fedora-base:latest'
        container_build_path = WORK_DIR + '/' + 'fedora-base'
        logfile = '/tmp/kolla/fedora-base/fedora-base-build.log'
        buildah_cmd_build = ['bud', '--tls-verify=False', '--logfile',
                             logfile, '-t', dest, container_build_path]
        args.extend(buildah_cmd_build)
        bb(WORK_DIR, DEPS).build('fedora-base', container_build_path)
        mock_process.assert_called_once_with(
            *args, run_as_root=False, use_standard_locale=True
        )

    @mock.patch.object(process, 'execute', autospec=True)
    def test_push(self, mock_process):
        args = copy.copy(BUILDAH_CMD_BASE)
        dest = '127.0.0.1:8787/master/fedora-binary-fedora-base:latest'
        buildah_cmd_push = ['push', '--tls-verify=False', dest,
                            'docker://' + dest]
        args.extend(buildah_cmd_push)
        bb(WORK_DIR, DEPS).push(dest)
        mock_process.assert_called_once_with(
            *args, run_as_root=False, use_standard_locale=True
        )

    @mock.patch.object(bb, 'build', autospec=True)
    @mock.patch.object(bb, 'push', autospec=True)
    def test_generate_container_with_push(self, mock_push, mock_build):
        container_name = "fedora-base"
        destination = "127.0.0.1:8787/master/fedora-binary-{}:latest"
        builder = bb(WORK_DIR, DEPS, push_containers=True)
        builder._generate_container(container_name)
        mock_build.assert_called_once_with(builder, container_name, "")
        mock_push.assert_called_once_with(builder,
                                          destination.format(container_name))

    @mock.patch.object(bb, 'build', autospec=True)
    @mock.patch.object(bb, 'push', autospec=True)
    def test_generate_container_without_push(self, mock_push, mock_build):
        container_name = "fedora-base"
        builder = bb(WORK_DIR, DEPS, push_containers=False)
        builder._generate_container(container_name)
        mock_build.assert_called_once_with(builder, container_name, "")
        assert not mock_push.called
