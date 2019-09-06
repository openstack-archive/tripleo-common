#!/usr/bin/env python

# Copyright 2019 Red Hat, Inc.
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

from collections import OrderedDict
import os.path
import yaml


class TemplateDumper(yaml.SafeDumper):
    def represent_ordered_dict(self, data):
        return self.represent_dict(data.items())


TemplateDumper.add_representer(OrderedDict,
                               TemplateDumper.represent_ordered_dict)


class TripleoInventories(object):
    def __init__(self, stack_to_inv_obj_map):
        """
        Input: a mapping of stack->TripleoInventory objects, e.g.
          stack_to_inv_obj_map['central'] = TripleoInventory('central')
          stack_to_inv_obj_map['edge0'] = TripleoInventory('edge0')
        """
        self.stack_to_inv_obj_map = stack_to_inv_obj_map
        self.inventory = OrderedDict()

    def merge(self):
        """Merge TripleoInventory objects into self.inventory"""
        for stack, inv_obj in self.stack_to_inv_obj_map.items():
            # convert each inventory object into an ordered dict
            inv = inv_obj.list()
            # only want one undercloud, shouldn't matter which
            if 'Undercloud' not in self.inventory.keys():
                self.inventory['Undercloud'] = inv['Undercloud']
                self.inventory['Undercloud']['hosts'] = {'undercloud': {}}
                # add 'plans' to create a list to append to
                self.inventory['Undercloud']['vars']['plans'] = []

            # save the plan for this stack in the plans list
            plan = inv['Undercloud']['vars']['plan']
            self.inventory['Undercloud']['vars']['plans'].append(plan)

            for key in inv.keys():
                if key != 'Undercloud':
                    new_key = stack + '_' + key
                    if 'children' in inv[key].keys():
                        roles = []
                        for child in inv[key]['children']:
                            roles.append(stack + '_' + child)
                        self.inventory[new_key] = {}
                        self.inventory[new_key]['vars'] = inv[key]['vars']
                        for role in roles:
                            self.inventory[new_key]['children'] = {}
                            self.inventory[new_key]['children'][role] = {}
                        if key == 'overcloud':
                            # useful to have just stack name refer to children
                            self.inventory[stack] = self.inventory[new_key]
                    else:
                        if key != '_meta':
                            self.inventory[new_key] = inv[key]
                            self.inventory[new_key]['hosts'] = {}
                            self.inventory[new_key]['hosts'] = \
                                inv['_meta']['hostvars']

        # 'plan' doesn't make sense when using multiple plans
        self.inventory['Undercloud']['vars']['plan'] = ''
        # sort plans list for consistency
        self.inventory['Undercloud']['vars']['plans'].sort()

    def write_static_inventory(self, inventory_file_path, extra_vars=None):
        """Convert OrderedDict inventory to static yaml format in a file."""
        allowed_extensions = ('.yaml', '.yml', '.json')
        if not os.path.splitext(inventory_file_path)[1] in allowed_extensions:
            raise ValueError("Path %s does not end with one of %s extensions"
                             % (inventory_file_path,
                                ",".join(allowed_extensions)))

        if extra_vars:
            for var, value in extra_vars.items():
                if var in self.inventory:
                    self.inventory[var]['vars'].update(value)

        with open(inventory_file_path, 'w') as inventory_file:
            yaml.dump(self.inventory, inventory_file, TemplateDumper)

    def host(self):
        # Dynamic inventory scripts must return empty json if they don't
        # provide detailed info for hosts:
        # http://docs.ansible.com/ansible/developing_inventory.html
        return {}
