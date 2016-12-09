# Copyright 2016 Red Hat, Inc.
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

from tripleo_common import constants


def empty_container(swiftclient, name):
    container_names = [container["name"] for container
                       in swiftclient.get_account()[1]]

    if name in container_names:
        headers, objects = swiftclient.get_container(name)
        # ensure container is a plan
        if headers.get(constants.TRIPLEO_META_USAGE_KEY) != 'plan':
            error_text = ("The {name} container does not contain a "
                          "TripleO deployment plan and was not "
                          "deleted.".format(name=name))
            raise ValueError(error_text)
        else:
            # FIXME(rbrady): remove delete_object loop when
            # LP#1615830 is fixed.  See LP#1615825 for more info.
            # delete files from plan
            for o in objects:
                swiftclient.delete_object(name, o['name'])
    else:
        error_text = "The {name} container does not exist.".format(name=name)
        raise ValueError(error_text)


def delete_container(swiftclient, name):
    empty_container(swiftclient, name)
    swiftclient.delete_container(name)
