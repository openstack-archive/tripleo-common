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

# TRIPLEO_META_USAGE_KEY is inserted into metadata for containers created in
# Swift via SwiftPlanStorageBackend to identify them from other containers
TRIPLEO_META_USAGE_KEY = 'x-container-meta-usage-tripleo'

# OBJECT_META_KEY_PREFIX is used to prefix Swift metadata keys per object
# in SwiftPlanStorageBackend
OBJECT_META_KEY_PREFIX = 'x-object-meta-'

# The following keys are used when identifying metadata from the capabilities
# map file
ROOT_TEMPLATE_META = {'file-type': 'root-template'}
ROOT_ENVIRONMENT_META = {'file-type': 'root-environment', 'enabled': 'True'}
ENVIRONMENT_META = {'file-type': 'environment'}
