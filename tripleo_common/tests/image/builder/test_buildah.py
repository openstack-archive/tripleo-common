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
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor as tpe
from unittest import mock

from tripleo_common.image.builder.buildah import BuildahBuilder as bb
from tripleo_common.tests import base
from tripleo_common.utils import process


BUILDAH_CMD_BASE = ['sudo', 'buildah']
DEPS = {"base"}
WORK_DIR = '/tmp/kolla'
VOLS = ['/etc/pki:/etc/pki', '/etc/dir2:/dir2']
BUILD_ALL_LIST_CONTAINERS = ['container1', 'container2', 'container3']
BUILD_ALL_DICT_CONTAINERS = {
    'container1': {},
    'container2': {},
    'container3': {}
}
BUILD_ALL_STR_CONTAINER = 'container1'

PREPROCESSED_CONTAINER_DEPS = [
    {
        "image0": [
            "image1",
            {
                "image2": [
                    {
                        "image3": [
                            "image4",
                            "image5"
                        ]
                    },
                    "image8",
                    {
                        "image6": [
                            "image7"
                        ]
                    },
                    "image9"
                ]
            },
            {
                "image10": [
                    "image11",
                    "image12"
                ]
            },
            "image13",
            "image14"
        ]
    }
]


class ThreadPoolExecutorReturn(object):
    _exception = None


class ThreadPoolExecutorReturnFailed(object):
    _exception = True
    exception_info = "This is a test failure"


class ThreadPoolExecutorReturnSuccess(object):
    _exception = False


# Iterable version of the return values for predictable submit() returns
R_FAILED_LIST = [ThreadPoolExecutorReturnSuccess(),
                 ThreadPoolExecutorReturnSuccess(),
                 ThreadPoolExecutorReturnFailed()]
R_OK_LIST = [ThreadPoolExecutorReturnSuccess(),
             ThreadPoolExecutorReturnSuccess(),
             ThreadPoolExecutorReturnSuccess()]
R_BROKEN_LISTS = [[ThreadPoolExecutorReturnSuccess()],
                  [ThreadPoolExecutorReturn(),
                   ThreadPoolExecutorReturn()]]

# Return values as done and not_done sets for the ThreadPoolExecutor
R_FAILED = (set(R_FAILED_LIST), set())
R_OK = (set(R_OK_LIST), set())
R_BROKEN = (set(R_BROKEN_LISTS[0]), set(R_BROKEN_LISTS[1]))


class TestBuildahBuilder(base.TestCase):

    @mock.patch.object(process, 'execute', autospec=True)
    def test_build(self, mock_process):
        args = copy.copy(BUILDAH_CMD_BASE)
        dest = '127.0.0.1:8787/master/fedora-binary-fedora-base:latest'
        container_build_path = WORK_DIR + '/' + 'fedora-base'
        logfile = '/tmp/kolla/fedora-base/fedora-base-build.log'
        buildah_cmd_build = ['bud', '--format', 'docker',
                             '--tls-verify=False', '--logfile',
                             logfile, '-t', dest, container_build_path]
        args.extend(buildah_cmd_build)
        bb(WORK_DIR, DEPS).build('fedora-base', container_build_path)
        mock_process.assert_called_once_with(
            *args,
            check_exit_code=True,
            run_as_root=False,
            use_standard_locale=True
        )

    @mock.patch.object(process, 'execute', autospec=True)
    def test_build_without_img_type(self, mock_process):
        args = copy.copy(BUILDAH_CMD_BASE)
        dest = '127.0.0.1:8787/master/fedora-fedora-base:latest'
        container_build_path = WORK_DIR + '/' + 'fedora-base'
        logfile = '/tmp/kolla/fedora-base/fedora-base-build.log'
        buildah_cmd_build = ['bud', '--format', 'docker',
                             '--tls-verify=False', '--logfile',
                             logfile, '-t', dest, container_build_path]
        args.extend(buildah_cmd_build)
        bb(WORK_DIR, DEPS, img_type=False).build('fedora-base',
                                                 container_build_path)
        mock_process.assert_called_once_with(
            *args,
            check_exit_code=True,
            run_as_root=False,
            use_standard_locale=True
        )

    @mock.patch.object(process, 'execute', autospec=True)
    def test_build_with_volumes(self, mock_process):
        args = copy.copy(BUILDAH_CMD_BASE)
        dest = '127.0.0.1:8787/master/fedora-binary-fedora-base:latest'
        container_build_path = WORK_DIR + '/' + 'fedora-base'
        logfile = '/tmp/kolla/fedora-base/fedora-base-build.log'
        buildah_cmd_build = ['bud', '--volume', '/etc/pki:/etc/pki',
                             '--volume', '/etc/dir2:/dir2',
                             '--format', 'docker',
                             '--tls-verify=False', '--logfile',
                             logfile, '-t', dest, container_build_path]
        args.extend(buildah_cmd_build)
        bb(WORK_DIR, DEPS, volumes=VOLS).build('fedora-base',
                                               container_build_path)
        mock_process.assert_called_once_with(
            *args,
            check_exit_code=True,
            run_as_root=False,
            use_standard_locale=True
        )

    @mock.patch.object(process, 'execute', autospec=True)
    def test_build_with_excludes(self, mock_process):
        bb(WORK_DIR, DEPS, excludes=['fedora-base'])._generate_container(
            'fedora-base')
        assert not mock_process.called

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

    @mock.patch.object(tpe, 'submit', autospec=True)
    @mock.patch.object(futures, 'wait', autospec=True, return_value=R_BROKEN)
    @mock.patch.object(process, 'execute', autospec=True)
    def test_build_all_list_broken(self, mock_build, mock_wait, mock_submit):
        mock_submit.side_effect = R_BROKEN_LISTS[0] + R_BROKEN_LISTS[1]
        _b = bb(WORK_DIR, DEPS)
        self.assertRaises(
            SystemError,
            _b.build_all,
            deps=BUILD_ALL_LIST_CONTAINERS
        )

    @mock.patch.object(tpe, 'submit', autospec=True)
    @mock.patch.object(futures, 'wait', autospec=True, return_value=R_FAILED)
    @mock.patch.object(process, 'execute', autospec=True)
    def test_build_all_list_failed(self, mock_build, mock_wait, mock_submit):
        mock_submit.side_effect = R_FAILED_LIST
        _b = bb(WORK_DIR, DEPS)
        self.assertRaises(
            RuntimeError,
            _b.build_all,
            deps=BUILD_ALL_LIST_CONTAINERS
        )

    @mock.patch.object(tpe, 'submit', autospec=True)
    @mock.patch.object(futures, 'wait', autospec=True, return_value=R_OK)
    @mock.patch.object(process, 'execute', autospec=True)
    def test_build_all_list_ok(self, mock_build, mock_wait, mock_submit):
        bb(WORK_DIR, DEPS).build_all(deps=BUILD_ALL_LIST_CONTAINERS)

    @mock.patch.object(tpe, 'submit', autospec=True)
    @mock.patch.object(futures, 'wait', autospec=True, return_value=R_OK)
    @mock.patch.object(process, 'execute', autospec=True)
    def test_build_all_ok_no_deps(self, mock_build, mock_wait, mock_submit):
        bb(WORK_DIR, DEPS).build_all()

    @mock.patch.object(tpe, 'submit', autospec=True)
    @mock.patch.object(futures, 'wait', autospec=True, return_value=R_OK)
    @mock.patch.object(process, 'execute', autospec=True)
    def test_build_all_dict_ok(self, mock_build, mock_wait, mock_submit):
        bb(WORK_DIR, DEPS).build_all(deps=BUILD_ALL_DICT_CONTAINERS)

    @mock.patch.object(tpe, 'submit', autospec=True)
    @mock.patch.object(futures, 'wait', autospec=True, return_value=R_OK)
    @mock.patch.object(process, 'execute', autospec=True)
    def test_build_all_str_ok(self, mock_build, mock_wait, mock_submit):
        bb(WORK_DIR, DEPS).build_all(deps=BUILD_ALL_STR_CONTAINER)

    def test_dep_processing(self):
        containers = list()
        self.assertEqual(
            bb(WORK_DIR, DEPS)._generate_deps(
                deps=PREPROCESSED_CONTAINER_DEPS,
                containers=containers
            ),
            [
                [
                    'image0'
                ],
                [
                    'image1',
                    'image13',
                    'image14',
                    'image2',
                    'image10'
                ],
                [
                    'image8',
                    'image9',
                    'image3',
                    'image6'
                ],
                [
                    'image4',
                    'image5'
                ],
                [
                    'image7'
                ],
                [
                    'image11',
                    'image12'
                ]
            ]
        )

    @mock.patch(
        'tripleo_common.image.builder.buildah.BuildahBuilder._multi_build',
        autospec=True
    )
    def test_build_all_multi_build(self, mock_multi_build):
        bb(WORK_DIR, DEPS).build_all(deps=BUILD_ALL_LIST_CONTAINERS)
        self.assertTrue(mock_multi_build.called)
