# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import collections
import fixtures
import os
from unittest.mock import MagicMock

import yaml

from tripleo_common.tests import base
from tripleo_common.inventories import TripleoInventories


class _TestInventoriesBase(base.TestCase):
    def setUp(self):
        super(_TestInventoriesBase, self).setUp()
        self.read_inventory_data()

    def read_inventory_data(self):
        inventory_data = collections.OrderedDict()
        inventory_dir = os.path.join(
            os.path.dirname(__file__), 'inventory_data'
        )
        for datafile in (
                'cell1_dynamic.json',
                'cell1_static.yaml',
                'overcloud_dynamic.json',
                'overcloud_static.yaml',
                'merged_dynamic.json',
                'merged_static.yaml',
                'single_dynamic.json',
                'single_static.yaml',
                'undercloud_dynamic.json',
                'undercloud_static.yaml',
                'undercloud_dynamic_merged.json',
                'undercloud_static_merged.yaml',
                ):
            name = os.path.basename(datafile).split('.')[0]
            path = os.path.join(inventory_dir, datafile)
            with open(path, 'r') as data:
                inventory_data[name] = yaml.safe_load(data)
        self.inventory_data = inventory_data


class TestInventoriesStatic(_TestInventoriesBase):
    def setUp(self):
        super(TestInventoriesStatic, self).setUp()
        mock_inv_overcloud = MagicMock()
        mock_inv_cell1 = MagicMock()
        mock_inv_overcloud.list.return_value = self.inventory_data[
            'overcloud_static'
        ]
        mock_inv_cell1.list.return_value = self.inventory_data[
            'cell1_static'
        ]
        stack_to_inv_obj_map = {
            'overcloud': mock_inv_overcloud,
            'cell1': mock_inv_cell1
            }
        self.inventories = TripleoInventories(stack_to_inv_obj_map)

    def test_merge(self):
        actual = dict(self.inventories._merge(dynamic=False))
        expected = self.inventory_data['merged_static']
        self.assertEqual(expected, actual)

    def test_inventory_write_static(self):
        tmp_dir = self.useFixture(fixtures.TempDir()).path
        inv_path = os.path.join(tmp_dir, "inventory.yaml")
        self.inventories.write_static_inventory(inv_path)
        expected = self.inventory_data['merged_static']
        with open(inv_path, 'r') as f:
            loaded_inv = collections.OrderedDict(yaml.safe_load(f))
        self.assertEqual(expected, loaded_inv)


class TestInventoriesDynamic(_TestInventoriesBase):
    def setUp(self):
        super(TestInventoriesDynamic, self).setUp()
        mock_inv_overcloud = MagicMock()
        mock_inv_cell1 = MagicMock()
        mock_inv_overcloud.list.return_value = self.inventory_data[
            'overcloud_dynamic'
        ]
        mock_inv_cell1.list.return_value = self.inventory_data[
            'cell1_dynamic'
        ]
        stack_to_inv_obj_map = {
            'overcloud': mock_inv_overcloud,
            'cell1': mock_inv_cell1
            }
        self.inventories = TripleoInventories(stack_to_inv_obj_map)

    def test_merge(self):
        actual = dict(self.inventories._merge())
        expected = dict(self.inventory_data['merged_dynamic'])
        self.assertEqual(expected, actual)

    def test_list(self):
        actual = self.inventories.list()
        expected = self.inventory_data['merged_dynamic']
        self.assertEqual(expected, actual)


class TestInventorySingleStatic(_TestInventoriesBase):
    def setUp(self):
        super(TestInventorySingleStatic, self).setUp()
        mock_inv_overcloud = MagicMock()
        mock_inv_overcloud.list.return_value = self.inventory_data[
            'overcloud_static'
        ]
        stack_to_inv_obj_map = {
            'overcloud': mock_inv_overcloud
        }
        self.inventories = TripleoInventories(stack_to_inv_obj_map)

    def test_list(self):
        actual = self.inventories.list()
        expected = self.inventory_data['single_static']
        self.assertEqual(expected, actual)


class TestInventorySingleDynamic(_TestInventoriesBase):
    def setUp(self):
        super(TestInventorySingleDynamic, self).setUp()
        mock_inv_overcloud = MagicMock()
        mock_inv_overcloud.list.return_value = self.inventory_data[
            'overcloud_dynamic'
        ]
        stack_to_inv_obj_map = {
            'overcloud': mock_inv_overcloud
        }
        self.inventories = TripleoInventories(stack_to_inv_obj_map)

    def test_list(self):
        actual = self.inventories.list()
        expected = self.inventory_data['single_dynamic']
        self.assertEqual(expected, actual)


class TestInventoryUndercloudStatic(_TestInventoriesBase):
    def setUp(self):
        super(TestInventoryUndercloudStatic, self).setUp()
        mock_inv_undercloud = MagicMock()
        mock_inv_undercloud.list.return_value = self.inventory_data[
            'undercloud_static'
        ]
        stack_to_inv_obj_map = {
            'foobar': mock_inv_undercloud
        }
        self.inventories = TripleoInventories(stack_to_inv_obj_map)

    def test_list(self):
        actual = self.inventories.list(dynamic=False)
        expected = self.inventory_data['undercloud_static_merged']
        self.assertEqual(expected, actual)


class TestInventoryUndercloudDynamic(_TestInventoriesBase):
    def setUp(self):
        super(TestInventoryUndercloudDynamic, self).setUp()
        mock_inv_undercloud = MagicMock()
        mock_inv_undercloud.list.return_value = self.inventory_data[
            'undercloud_dynamic'
        ]
        stack_to_inv_obj_map = {
            'foobar': mock_inv_undercloud
        }
        self.inventories = TripleoInventories(stack_to_inv_obj_map)

    def test_list(self):
        actual = self.inventories.list()
        expected = self.inventory_data['undercloud_dynamic_merged']
        self.assertEqual(expected, actual)
