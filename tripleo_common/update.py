# Copyright 2015 Red Hat, Inc.
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

from six import iteritems
import yaml

from heatclient.common import template_utils

from tripleo_common import constants
from tripleo_common.utils import swift as swiftutils


def add_breakpoints_cleanup_into_env(env):
    template_utils.deep_update(env, {
        'resource_registry': {
            'resources': {'*': {'*': {
                constants.UPDATE_RESOURCE_NAME: {'hooks': []}}}}
        }
    })


def search_stack(stack_data, key_name):
    if isinstance(stack_data, list):
        for item in stack_data:
            result = search_stack(item, key_name)
            if result:
                return result
    elif isinstance(stack_data, dict):
        for k, v in iteritems(stack_data):
            if k == key_name:
                return v
            else:
                result = search_stack(v, key_name)
                if result:
                    return result


def get_exclusive_neutron_driver(drivers):
    if not drivers:
        return
    mutually_exclusive_drivers = constants.EXCLUSIVE_NEUTRON_DRIVERS
    if isinstance(drivers, str):
        drivers = [drivers]
    for d in mutually_exclusive_drivers:
        if d in drivers:
            return d


def check_neutron_mechanism_drivers(env, stack, plan_client, container):
    force_update = env.get('parameter_defaults').get(
        'ForceNeutronDriverUpdate', False)
    # Forcing an update and skip checks is need to support  migrating from one
    # driver to another
    if force_update:
        return

    driver_key = 'NeutronMechanismDrivers'
    current_drivers = search_stack(stack._info, driver_key)
    # TODO(beagles): We may need to move or copy this check earlier
    # to automagically pull in an openvswitch ML2 compatibility driver.
    current_driver = get_exclusive_neutron_driver(current_drivers)
    configured_drivers = env.get('parameter_defaults').get(driver_key)
    new_driver = None
    if configured_drivers:
        new_driver = get_exclusive_neutron_driver(configured_drivers)
    else:
        try:
            # TODO(beagles): we need to look for a better way to
            # get the current template default value. This is fragile
            # with respect to changing filenames, etc.
            ml2_tmpl = swiftutils.get_object_string(
                plan_client,
                container,
                'puppet/services/neutron-plugin-ml2.yaml')
            ml2_def = yaml.safe_load(ml2_tmpl)
            default_drivers = ml2_def.get(
                'parameters', {}).get(driver_key, {}).get('default')
            new_driver = get_exclusive_neutron_driver(default_drivers)
        except Exception:
            # NOTE: we restructured t-h-t in stein, if this happens we
            # assume neutron-plugin-ml2.yaml has been moved and
            # thus set the most recent default (OVN)
            new_driver = 'ovn'
    if current_driver and new_driver and current_driver != new_driver:
        msg = ("Unable to switch from {} to {} neutron "
               "mechanism drivers on upgrade. Please consult the "
               "documentation.").format(current_driver, new_driver)
        return msg
