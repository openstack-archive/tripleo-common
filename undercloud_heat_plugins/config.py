#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from heat.engine.resources.openstack.heat import software_deployment
from heat.engine.resources.openstack.heat import structured_config


class SoftwareDeployment(software_deployment.SoftwareDeployment):
    """A custom subclass to allow reverting replacement."""


class StructuredDeployment(structured_config.StructuredDeployment):
    """A custom subclass to allow reverting replacement."""


def resource_mapping():
    return {
        'OS::TripleO::Heat::SoftwareDeployment': SoftwareDeployment,
        'OS::TripleO::Heat::StructuredDeployment': StructuredDeployment
    }
