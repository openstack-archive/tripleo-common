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
import os
import tempfile
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

    def _merge(self, dynamic=True):
        """Merge TripleoInventory objects"""
        inventory = OrderedDict()
        if dynamic:
            inventory['_meta'] = {'hostvars': {}}
        for stack, inv_obj in self.stack_to_inv_obj_map.items():
            # convert each inventory object into an ordered dict
            inv = inv_obj.list(dynamic)
            # only want one undercloud, shouldn't matter which
            if 'Undercloud' not in inventory.keys():
                inventory['Undercloud'] = inv['Undercloud']
                if dynamic:
                    inventory['Undercloud']['hosts'] = ['undercloud']
                else:
                    inventory['Undercloud']['hosts'] = {'undercloud': {}}
                # add 'plans' to create a list to append to
                inventory['Undercloud']['vars']['plans'] = []

            # save the plan for this stack in the plans list
            plan = inv['Undercloud']['vars']['plan']
            if plan is not None:
                inventory['Undercloud']['vars']['plans'].append(plan)

            for key in inv.keys():
                if key != 'Undercloud':
                    new_key = stack + '_' + key

                    if key not in ('_meta', 'overcloud', stack):
                        # Merge into a top level group
                        if dynamic:
                            inventory.setdefault(key, {'children': []})
                            inventory[key]['children'].append(new_key)
                            inventory[key]['children'].sort()
                        else:
                            inventory.setdefault(key, {'children': {}})
                            inventory[key]['children'][new_key] = {}
                    if 'children' in inv[key].keys():
                        roles = []
                        for child in inv[key]['children']:
                            roles.append(stack + '_' + child)
                        roles.sort()
                        if dynamic:
                            inventory[new_key] = {
                                'children': roles
                            }
                        else:
                            inventory[new_key] = {
                                'children': {x: {} for x in roles}
                            }
                        if 'vars' in inv[key]:
                            inventory[new_key]['vars'] = inv[key]['vars']
                        if key == 'allovercloud':
                            # useful to have just stack name refer to children
                            if dynamic:
                                inventory[stack] = {'children': [new_key]}
                            else:
                                inventory[stack] = {'children': {new_key: {}}}
                    else:
                        if key != '_meta':
                            inventory[new_key] = inv[key]
                        elif dynamic:
                            inventory['_meta']['hostvars'].update(
                                inv['_meta'].get('hostvars', {})
                            )

        # 'plan' doesn't make sense when using multiple plans
        if len(self.stack_to_inv_obj_map) > 1:
            del inventory['Undercloud']['vars']['plan']
        # sort plans list for consistency
        inventory['Undercloud']['vars']['plans'].sort()
        return inventory

    def list(self, dynamic=True):
        return self._merge(dynamic)

    def write_static_inventory(self, inventory_file_path, extra_vars=None):
        """Convert OrderedDict inventory to static yaml format in a file."""
        allowed_extensions = ('.yaml', '.yml', '.json')
        if not os.path.splitext(inventory_file_path)[1] in allowed_extensions:
            raise ValueError("Path %s does not end with one of %s extensions"
                             % (inventory_file_path,
                                ",".join(allowed_extensions)))

        inventory = self._merge(dynamic=False)

        if extra_vars:
            for var, value in extra_vars.items():
                if var in inventory:
                    inventory[var]['vars'].update(value)

        # Atomic update as concurrent tripleoclient commands can call this
        inventory_file_dir = os.path.dirname(inventory_file_path)
        with tempfile.NamedTemporaryFile(
                'w',
                dir=inventory_file_dir,
                delete=False) as inventory_file:
            yaml.dump(inventory, inventory_file, TemplateDumper)
        os.rename(inventory_file.name, inventory_file_path)

    def host(self):
        # Dynamic inventory scripts must return empty json if they don't
        # provide detailed info for hosts:
        # http://docs.ansible.com/ansible/developing_inventory.html
        return {}
