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


def uploaded_layers_details(uploaded_layers, layer, scope):
    known_path = None
    known_layer = None
    image = None
    if layer:
        known_layer = uploaded_layers.get(layer, None)
        if known_layer and scope in known_layer:
            known_path = known_layer[scope].get('path', None)
            image = known_layer[scope].get('ref', None)
    return (known_path, image)
