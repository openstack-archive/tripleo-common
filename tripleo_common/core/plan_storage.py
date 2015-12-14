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
from tripleo_common.core import constants
from tripleo_common.core import exception
from tripleo_common.core.models import Plan
from tripleo_common.utils import meta

default_container_headers = {
    'X-Versions-Location': 'versions',
    constants.TRIPLEO_META_USAGE_KEY: 'plan'
}


class SwiftPlanStorageBackend(object):
    def __init__(self, swiftclient):
        self.swiftclient = swiftclient

    def create(self, plan_name):
        """Creates a plan to store files

        Creates a plan by creating a Swift container matching plan_name, and
        given files into it.

        :param plan_name: The name of the plan
        :type plan_name: str
        :param plan_files: names and contents of files to store
        :type plan_files: dict
        """
        if plan_name not in self.list():
            self.swiftclient.put_container(
                plan_name,
                headers=default_container_headers
            )
        else:
            raise exception.PlanAlreadyExistsError(name=plan_name)

    def delete(self, plan_name):
        """Deletes a plan and associated files

        Deletes a plan by deleting the Swift container matching plan_name.

        :param plan_name: The name of the plan
        :type plan_name: str
        """
        # delete files from plan
        for data in self.swiftclient.get_container(plan_name)[1]:
            self.swiftclient.delete_object(plan_name, data['name'])
        # delete plan container
        self.swiftclient.delete_container(plan_name)

    def delete_file(self, plan_name, filepath):
        """Deletes a file for a given filepath from a plan container

        :param plan_name: The name of the plan
        :type plan_name: str
        :param filepath: The path of the file to be deleted
        """
        self.swiftclient.delete_object(plan_name, filepath)

    def get(self, plan_name):
        """Retrieves the files for a given container name

        Retrieves the files from the Swift container matching plan_name.

        :param plan_name: The name of the plan
        :type plan_name: str
        :return: a list of files
        :rtype list
        """
        plan = Plan(plan_name)
        container = self.swiftclient.get_container(plan_name)
        plan.metadata = container[0]
        for data in container[1]:
            filename = data['name']
            plan_obj = self.swiftclient.get_object(plan_name, filename)
            plan.files[filename] = {}
            plan.files[filename]['contents'] = plan_obj[1]
            meta_info = {k: v for (k, v) in plan_obj[0].items()
                         if constants.OBJECT_META_KEY_PREFIX in k}
            if len(meta_info) > 0:
                plan.files[filename]['meta'] = \
                    meta.remove_key_prefix(meta_info)

        return plan

    def list(self):
        """Gets a list of containers that store plans

        Gets a list of containers that contain metadata with the key of
        X-Container-Meta-Usage-Tripleo and value or 'plan'.

        :return: a list of strings containing plan names
        """
        plan_list = []
        for item in self.swiftclient.get_account()[1]:
            container = self.swiftclient.get_container(item['name'])[0]
            if constants.TRIPLEO_META_USAGE_KEY in container.keys():
                plan_list.append(item['name'])

        return plan_list

    def update(self, plan_name, plan_files):
        """Updates a plan by updating the files in container

        Updates a plan by updating the files in the Swift container
        matching plan_name.

        :param plan_name: The name of the plan
        :type plan_name: str
        :param plan_files: names and contents of files to store
        :type plan_files: dict
        """

        for filename, details in plan_files.items():
            custom_headers = {}
            if 'meta' in details:
                custom_headers = meta.add_key_prefix(details['meta'])
            self.swiftclient.put_object(
                plan_name,
                filename,
                details['contents'],
                headers=custom_headers
            )
