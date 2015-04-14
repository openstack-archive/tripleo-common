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

import logging
import os
import tempfile

LOG = logging.getLogger(__name__)


def save_templates(templates):
    output_dir = tempfile.mkdtemp()

    for template_name, template_content in templates.items():

        # It's possible to organize the role templates and their dependent
        # files into directories, in which case the template_name will carry
        # the directory information. If that's the case, first create the
        # directory structure (if it hasn't already been created by another
        # file in the templates list).
        template_dir = os.path.dirname(template_name)
        output_template_dir = os.path.join(output_dir, template_dir)
        if template_dir and not os.path.exists(output_template_dir):
            os.makedirs(output_template_dir)

        filename = os.path.join(output_dir, template_name)
        with open(filename, 'w+') as template_file:
            template_file.write(template_content)
    return output_dir
