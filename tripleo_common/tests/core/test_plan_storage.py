# Copyright 2015 Red Hat, Inc.
# All Rights Reserved.
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
import mock

from tripleo_common.core import exception
from tripleo_common.core.models import Plan
from tripleo_common.core.plan_storage import default_container_headers
from tripleo_common.core.plan_storage import SwiftPlanStorageBackend
from tripleo_common.tests import base

PLAN_DATA = {
    '/path/to/overcloud.yaml': {
        'contents': "heat_template_version: 2015-04-30\n\n"
                    "resources:\n"
                    "\n"
                    "  HorizonSecret:\n"
                    "    type: OS::Heat::RandomString\n"
                    "    properties:\n"
                    "      length: 10\n"
                    "\n"
                    "  Controller:\n"
                    "    type: OS::Heat::ResourceGroup\n"
                    "    depends_on: Networks\n"
                    "    properties:\n"
                    "      count: {get_param: ControllerCount}\n",
        'meta': {'file-type': 'root-template'},
    },
    '/path/to/environment.yaml': {
        'contents': "parameters:\n"
                    "  one: uno\n"
                    "  obj:\n"
                    "    two: due\n"
                    "    three: tre\n",
        'meta': {'file-type': 'root-environment'},
    },
    '/path/to/network-isolation.json': {
        'contents': '{"parameters": {"one": "one"}}',
        'meta': {'file-type': 'environment', 'order': 1},
    },
    '/path/to/ceph-storage-env.yaml': {
        'contents': "parameters:\n"
                    "  obj:\n"
                    "    two: dos,\n"
                    "    three: three",
        'meta': {'file-type': 'environment', 'order': 2},
    },
    '/path/to/poc-custom-env.yaml': {
        'contents': "parameters:\n"
                    "  obj:\n"
                    "    two: two\n"
                    "  some::resource: /path/to/somefile.yaml",
        'meta': {'file-type': 'environment', 'order': 0}
    },
    '/path/to/somefile.yaml': {'contents': "description: lorem ipsum"}
}


class PlanStorageTest(base.TestCase):

    def setUp(self):
        super(PlanStorageTest, self).setUp()
        self.swiftclient = mock.MagicMock()
        self.plan_store = SwiftPlanStorageBackend(self.swiftclient)
        self.plan_name = "overcloud"

    def test_create(self):
        # create a plan
        self.plan_store.list = mock.MagicMock(return_value=['test1', 'test2'])
        self.swiftclient.put_container = mock.MagicMock()
        self.plan_store.create(self.plan_name)
        self.swiftclient.put_container.assert_called_with(
            self.plan_name,
            headers=default_container_headers
        )

        # attempt to create a 2nd plan should fail
        self.plan_store.list = mock.MagicMock(return_value=['overcloud'])
        self.assertRaisesRegexp(exception.PlanAlreadyExistsError,
                                self.plan_name,
                                self.plan_store.create,
                                self.plan_name)

    def test_delete(self):
        self.swiftclient.get_container = mock.MagicMock(
            return_value=({}, [
                {'name': 'some-name.yaml'},
                {'name': 'some-other-name.yaml'},
                {'name': 'yet-some-other-name.yaml'},
                {'name': 'finally-another-name.yaml'}
            ])
        )
        self.swiftclient.delete_object = mock.MagicMock()
        self.plan_store.delete(self.plan_name)
        mock_calls = [
            mock.call('overcloud', 'some-name.yaml'),
            mock.call('overcloud', 'some-other-name.yaml'),
            mock.call('overcloud', 'yet-some-other-name.yaml'),
            mock.call('overcloud', 'finally-another-name.yaml')
        ]
        self.swiftclient.delete_object.assert_has_calls(
            mock_calls, any_order=True)

    def test_delete_file(self):
        self.swiftclient.delete_object = mock.MagicMock()
        filepath = '/a/random/path/to/file.yaml'
        self.plan_store.delete_file(self.plan_name, filepath)
        self.swiftclient.delete_object.assert_called_with(
            self.plan_name, filepath)

    def test_get(self):
        metadata = {
            'x-container-meta-usage-tripleo': 'plan',
            'accept-ranges': 'bytes',
            'x-storage-policy': 'Policy-0',
            'connection': 'keep-alive',
            'x-timestamp': '1447161410.72641',
            'x-trans-id': 'tx1f41a9d34a2a437d8f8dd-00565dd486',
            'content-type': 'application/json; charset=utf-8',
            'x-versions-location': 'versions'
        }
        expected_plan = Plan(self.plan_name)
        expected_plan.metadata = metadata
        expected_plan.files = {
            'some-name.yaml': {
                'contents': "some fake contents",
                'meta': {'file-type': 'environment'}
            },
        }
        self.swiftclient.get_container = mock.MagicMock(return_value=(
            metadata, [
                {'name': 'some-name.yaml'},
            ])
        )
        self.swiftclient.get_object = mock.MagicMock(return_value=(
            {'x-object-meta-file-type': 'environment'}, "some fake contents"
        ))
        self.assertEqual(expected_plan.name,
                         self.plan_store.get(self.plan_name).name)
        self.swiftclient.get_container.assert_called_with(self.plan_name)
        self.swiftclient.get_object.assert_called_with(
            'overcloud', 'some-name.yaml')

    def test_list(self):
        self.swiftclient.get_account = mock.MagicMock(
            return_value=({}, [
                {
                    'count': 1,
                    'bytes': 55,
                    'name': 'overcloud'
                },
            ])
        )
        self.swiftclient.get_container = mock.MagicMock(
            return_value=({
                'x-container-meta-usage-tripleo': 'plan',
            }, [])
        )
        self.assertEqual(['overcloud'], self.plan_store.list())
        self.swiftclient.get_container.assert_called_with('overcloud')

    def test_update(self):
        expected_plan = Plan(self.plan_name)
        expected_plan.metadata = {
            'x-container-meta-usage-tripleo': 'plan',
            'accept-ranges': 'bytes',
            'x-storage-policy': 'Policy-0',
        }
        expected_plan.files = {
            'some-name.yaml': {
                'contents': "some fake contents",
                'meta': {'file-type': 'environment'}
            },
        }
        self.swiftclient.put_object = mock.MagicMock()
        self.plan_store.update(self.plan_name, expected_plan.files)
        self.swiftclient.put_object.assert_called_with(
            self.plan_name,
            'some-name.yaml',
            "some fake contents",
            headers={'x-object-meta-file-type': 'environment'}
        )
