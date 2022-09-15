# Copyright 2016 Red Hat, Inc.
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
import yaml

from mistral_lib import actions
from swiftclient import exceptions as swiftexceptions

from tripleo_common.actions import heat_capabilities
from tripleo_common.tests import base


MAPPING_YAML_CONTENTS = """topics:
  - title: Fake Single Environment Group Configuration
    description:
    environment_groups:
      - title:
        description: Random fake string of text
        environments:
          - file: /path/to/network-isolation.json
            title: Default Configuration
            description:

  - title: Fake Multiple Environment Group Configuration
    description:
    environment_groups:
      - title: Random Fake 1
        description: Random fake string of text
        environments:
          - file: /path/to/ceph-storage-env.yaml
            title: Fake1
            description: Random fake string of text

      - title: Random Fake 2
        description:
        environments:
          - file: /path/to/poc-custom-env.yaml
            title: Fake2
            description:
"""

MAPPING_JSON_CONTENTS = """{
  "Fake Multiple Environment Group Configuration": {
    "description": null,
    "environment_groups": [
      {
        "description": "Random fake string of text",
        "environments": [
          {
            "description": "Random fake string of text",
            "enabled": false,
            "file": "/path/to/ceph-storage-env.yaml",
            "title": "Fake1"
          }
        ],
        "title": "Random Fake 1"
      },
      {
        "description": null,
        "environments": [
          {
            "description": null,
            "enabled": false,
            "file": "/path/to/poc-custom-env.yaml",
            "title": "Fake2"
          }
        ],
        "title": "Random Fake 2"
      }
    ],
    "title": "Fake Multiple Environment Group Configuration"
  },
 "Fake Single Environment Group Configuration": {
   "description": null,
   "environment_groups": [
     {
       "description": "Random fake string of text",
       "environments": [
         {
           "description": null,
           "enabled": true,
           "file": "/path/to/network-isolation.json",
           "title": "Default Configuration"
         }
       ],
       "title": null
     }
   ],
  "title": "Fake Single Environment Group Configuration"
 },
 "Other": {
   "description": null,
   "environment_groups": [
     {
       "description": null,
       "environments": [
         {
        "description": "Enable /path/to/environments/custom.yaml environment",
           "enabled": false,
           "file": "/path/to/environments/custom.yaml",
           "title": "/path/to/environments/custom.yaml",
         }
       ],
       "title": "/path/to/environments/custom.yaml",
     },
     {
       "description": null,
       "environments": [
         {
        "description": "Enable /path/to/environments/custom2.yaml environment",
           "enabled": false,
           "file": "/path/to/environments/custom2.yaml",
           "title": "/path/to/environments/custom2.yaml",
         }
       ],
       "title": "/path/to/environments/custom2.yaml",
     }
   ],
  "title": "Other"
 }
}
"""


class GetCapabilitiesActionTest(base.TestCase):

    def setUp(self):
        super(GetCapabilitiesActionTest, self).setUp()
        self.container_name = 'test-container'

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_yaml_error(self, get_obj_client_mock):

        mock_ctx = mock.MagicMock()
        # setup swift
        swift = mock.MagicMock()
        swift.get_container.return_value = ({}, [])
        swift.get_object.return_value = mock.Mock(side_effect=ValueError)
        get_obj_client_mock.return_value = swift

        action = heat_capabilities.GetCapabilitiesAction(self.container_name)
        expected = actions.Result(
            data=None,
            error="Error parsing capabilities-map.yaml.")
        self.assertEqual(expected, action.run(mock_ctx))

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_env_missing(self, get_obj_client_mock):

        mock_ctx = mock.MagicMock()
        # setup swift
        swift = mock.MagicMock()
        swift.get_container.return_value = ({}, [])
        swift.get_object.side_effect = (
            ({}, MAPPING_YAML_CONTENTS),
            swiftexceptions.ClientException(self.container_name)
        )
        get_obj_client_mock.return_value = swift

        action = heat_capabilities.GetCapabilitiesAction(self.container_name)
        expected = actions.Result(
            data=None,
            error="Error retrieving environment for plan test-container: "
                  "test-container")
        self.assertEqual(expected, action.run(mock_ctx))

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, get_obj_client_mock):

        mock_ctx = mock.MagicMock()
        # setup swift
        swift = mock.MagicMock()

        mock_env = """
        template: overcloud
        environments:
        - path: /path/to/network-isolation.json
        """
        swift.get_object.side_effect = (
            ({}, MAPPING_YAML_CONTENTS),
            ({}, mock_env)
        )
        swift_container_metadata = {
            u'x-container-meta-usage-tripleo': u'plan',
            u'content-length': u'54271', u'x-container-object-count': u'3',
            u'accept-ranges': u'bytes', u'x-storage-policy': u'Policy-0',
            u'date': u'Wed, 31 Aug 2016 16:04:37 GMT',
            u'x-timestamp': u'1471025600.02126',
            u'x-trans-id': u'txebb37f980dbc4e4f991dc-0057c70015',
            u'x-container-bytes-used': u'970557',
            u'content-type': u'application/json; charset=utf-8'
        }
        swift_objects = [{
            u'bytes': 808,
            u'last_modified': u'2016-08-12T18:13:22.231760',
            u'hash': u'2df2606ed8b866806b162ab3fa9a77ea',
            u'name': 'all-nodes-validation.yaml',
            u'content_type': u'application/octet-stream'
        }, {
            u'bytes': 1808,
            u'last_modified': u'2016-08-13T18:13:22.231760',
            u'hash': u'3df2606ed8b866806b162ab3fa9a77ea',
            u'name': '/path/to/environments/custom.yaml',
            u'content_type': u'application/octet-stream'
        }, {
            u'bytes': 2808,
            u'last_modified': u'2016-07-13T18:13:22.231760',
            u'hash': u'4df2606ed8b866806b162ab3fa9a77ea',
            u'name': '/path/to/environments/custom2.yaml',
            u'content_type': u'application/octet-stream'
        }]
        swift.get_container.side_effect = [
            (swift_container_metadata, swift_objects),
            (swift_container_metadata, [])
        ]
        get_obj_client_mock.return_value = swift

        action = heat_capabilities.GetCapabilitiesAction(self.container_name)
        yaml_mapping = yaml.safe_load(MAPPING_JSON_CONTENTS)
        self.assertEqual(yaml_mapping, action.run(mock_ctx))


class UpdateCapabilitiesActionTest(base.TestCase):

    def setUp(self,):
        super(UpdateCapabilitiesActionTest, self).setUp()
        self.container_name = 'test-container'

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_delete')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run(self, get_object_client_mock, mock_cache):

        mock_ctx = mock.MagicMock()

        # setup swift
        swift = mock.MagicMock()
        mocked_env = """
        name: test-container
        environments:
        - path: /path/to/overcloud-default-env.yaml
        - path: /path/to/ceph-storage-env.yaml
        """
        swift.get_object.return_value = ({}, mocked_env)
        get_object_client_mock.return_value = swift

        environments = {
            '/path/to/ceph-storage-env.yaml': False,
            '/path/to/network-isolation.json': False,
            '/path/to/poc-custom-env.yaml': True
        }

        action = heat_capabilities.UpdateCapabilitiesAction(
            environments, self.container_name)
        self.assertEqual({
            'name': 'test-container',
            'environments': [
                {'path': '/path/to/overcloud-default-env.yaml'},
                {'path': '/path/to/poc-custom-env.yaml'}
            ]},
            action.run(mock_ctx))

        mock_cache.assert_called_once_with(
            mock_ctx,
            self.container_name,
            "tripleo.parameters.get"
        )

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_delete')
    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_with_sorting_environments(self, get_object_client_mock,
                                           mock_cache):
        mock_ctx = mock.MagicMock()

        # setup swift
        swift = mock.MagicMock()
        mocked_env = """
           name: test-container
           environments:
           - path: /path/to/overcloud-default-env.yaml
           - path: /path/to/ceph-storage-env.yaml
           """
        swift.get_object.side_effect = (
            ({}, mocked_env),
            ({}, MAPPING_YAML_CONTENTS))
        get_object_client_mock.return_value = swift

        environments = {
            '/path/to/ceph-storage-env.yaml': False,
            '/path/to/network-isolation.json': False,
            '/path/to/poc-custom-env.yaml': True
        }

        action = heat_capabilities.UpdateCapabilitiesAction(
            environments, self.container_name, sort_environments=True)
        self.assertEqual({
            'name': 'test-container',
            'environments': [
                {'path': '/path/to/poc-custom-env.yaml'},
                {'path': '/path/to/overcloud-default-env.yaml'}
            ]},
            action.run(mock_ctx))

        mock_cache.assert_called_once_with(
            mock_ctx,
            self.container_name,
            "tripleo.parameters.get"
        )

    @mock.patch('tripleo_common.actions.base.TripleOAction.'
                'cache_delete')
    @mock.patch(
        'tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_purge_missing(self, get_object_client_mock, mock_cache):

        mock_ctx = mock.MagicMock()

        # setup swift
        swift = mock.MagicMock()
        mocked_env = """
        name: test-container
        environments:
        - path: /path/to/overcloud-default-env.yaml
        - path: /path/to/ceph-storage-env.yaml
        """
        swift.get_object.return_value = ({}, mocked_env)
        get_object_client_mock.return_value = swift

        environments = {
            '/path/to/overcloud-default-env.yaml': True,
            '/path/to/network-isolation.json': False,
            '/path/to/poc-custom-env.yaml': True
        }

        action = heat_capabilities.UpdateCapabilitiesAction(
            environments, self.container_name, True)
        self.assertEqual({
            'name': 'test-container',
            'environments': [
                {'path': '/path/to/overcloud-default-env.yaml'},
                {'path': '/path/to/poc-custom-env.yaml'}
            ]},
            action.run(mock_ctx))
        mock_cache.assert_called_once_with(
            mock_ctx,
            self.container_name,
            "tripleo.parameters.get"
        )

    @mock.patch('tripleo_common.actions.base.TripleOAction.get_object_client')
    def test_run_env_missing(self, get_obj_client_mock):

        mock_ctx = mock.MagicMock()
        # setup swift
        swift = mock.MagicMock()
        swift.get_object.side_effect = (
            swiftexceptions.ClientException(self.container_name))
        get_obj_client_mock.return_value = swift

        action = heat_capabilities.UpdateCapabilitiesAction(
            {}, self.container_name)
        expected = actions.Result(
            data=None,
            error="Error retrieving environment for plan test-container: "
                  "test-container"
        )
        self.assertEqual(expected, action.run(mock_ctx))
