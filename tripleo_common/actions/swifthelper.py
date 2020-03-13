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

from mistral_lib import actions

from tripleo_common.actions import base
from tripleo_common.utils import swift as swiftutils


class SwiftInformationAction(base.TripleOAction):
    """Gets swift information for a given container

    This action gets the swift url for a container and an auth key that can be
    used to write to the container.
    """
    def __init__(self, container):
        super(SwiftInformationAction, self).__init__()
        self.container = container

    def run(self, context):
        data = None
        error = None
        try:
            oc = self.get_object_client(context)
            oc.head_container(self.container)
            container_url = "{}/{}".format(oc.url, self.container)
            auth_key = context.auth_token
            data = {'container_url': container_url, 'auth_key': auth_key}
        except Exception as err:
            error = str(err)

        return actions.Result(data=data, error=error)


class SwiftTempUrlAction(base.TripleOAction):

    def __init__(self, container, obj, method='GET', valid='86400'):
        super(SwiftTempUrlAction, self).__init__()
        self.container = container
        self.obj = obj
        self.method = method
        self.valid = valid

    def run(self, context):
        swift_client = self.get_object_client(context)
        return swiftutils.get_temp_url(
            swift_client, self.container, self.obj,
            self.method, self.valid)
