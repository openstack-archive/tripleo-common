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

import uuid

from mistral_lib import actions
from six.moves import urllib
from swiftclient import exceptions as swiftexceptions
from swiftclient.utils import generate_temp_url
from tripleo_common.actions import base


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

        try:
            cont_stat = swift_client.head_container(self.container)
        except swiftexceptions.ClientException:
            cont_stat = {}

        key = cont_stat.get('x-container-meta-temp-url-key')
        if not key:
            key = str(uuid.uuid4())
            cont_stat = swift_client.put_container(
                self.container, {'X-Container-Meta-Temp-Url-Key': key})
        parsed = urllib.parse.urlparse(swift_client.url)
        path = "%s/%s/%s" % (parsed.path, self.container, self.obj)
        temp_path = generate_temp_url(path, self.valid, key, self.method)
        return "%s://%s%s" % (parsed.scheme, parsed.netloc, temp_path)
