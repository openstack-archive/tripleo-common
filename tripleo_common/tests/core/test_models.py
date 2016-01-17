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
import datetime
import time

import six
import yaml

from tripleo_common.core.models import Plan
from tripleo_common.tests import base


class ModelTest(base.TestCase):

    def setUp(self):
        super(ModelTest, self).setUp()
        self.timestamp = time.time()

    def test_plan(self):
        plan = Plan('overcloud')
        plan.metadata = {
            'x-container-meta-usage-tripleo': 'plan',
            'accept-ranges': 'bytes',
            'x-storage-policy': 'Policy-0',
            'connection': 'keep-alive',
            'x-timestamp': self.timestamp,
            'x-trans-id': 'tx1f41a9d34a2a437d8f8dd-00565dd486',
            'content-type': 'application/json; charset=utf-8',
            'x-versions-location': 'versions'
        }
        plan.files = {
            'some-name.yaml': {
                'contents': "some fake contents",
                'meta': {'file-type': 'environment'}
            },
        }

        expected_date = datetime.datetime.fromtimestamp(
            float(self.timestamp))
        self.assertEqual(expected_date, plan.created_date(), "Date mismatch")

    def test_eq(self):
        self.assertEqual(Plan('foo'), Plan('foo'))
        self.assertNotEqual(Plan('bar'), Plan('foo'))
        self.assertNotEqual(Plan('bar'), None)

        class thing(object):
            pass

        self.assertNotEqual(Plan('bar'), thing())

    def test_repr(self):
        plan = Plan('foo')
        plan_str = six.text_type(plan)
        self.assertEqual({'Plan': {
            'files': {}, 'name': 'foo', 'metadata': {}
        }}, yaml.safe_load(plan_str))
