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
import datetime

import yaml


class BaseModel(object):

    def __repr__(self, *args, **kwargs):
        repr_ = {self.__class__.__name__: self.__dict__}
        return yaml.safe_dump(repr_, default_flow_style=True)

    def __eq__(self, other):
        if not (isinstance(other, self.__class__) or
                isinstance(self, other.__class__)):
            return False
        return self.__dict__ == getattr(other, '__dict__')


class Plan(BaseModel):

    def __init__(self, name):
        self.name = name
        self.files = {}
        self.metadata = {}

    def created_date(self):
        return datetime.datetime.fromtimestamp(
            float(self.metadata['x-timestamp']))
