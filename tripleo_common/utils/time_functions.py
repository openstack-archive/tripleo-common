# Copyright 2017 Red Hat, Inc.
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


def timestamp():
    """Return a UTC-now timestamp as a string"""
    return datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')


def epoch_to_formatted_date(epoch):
    """Convert an epoch time to a string"""
    epoch = float(epoch) / 1000
    dt = datetime.datetime.utcfromtimestamp(epoch)
    return dt.strftime('%Y-%m-%d %H:%M:%S')
