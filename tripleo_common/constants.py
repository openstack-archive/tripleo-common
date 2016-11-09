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


#: The names of the root template in a standard tripleo-heat-template layout.
OVERCLOUD_YAML_NAME = "overcloud.yaml"

#: The name of the overcloud root template in jinja2 format.
OVERCLOUD_J2_NAME = "overcloud.j2.yaml"

#: The name of custom roles data file used when rendering the jinja template.
OVERCLOUD_J2_ROLES_NAME = "roles_data.yaml"

#: The name of custom roles excl file used when rendering the jinja template.
OVERCLOUD_J2_EXCLUDES = "j2_excludes.yaml"

#: The name of the type for resource groups.
RESOURCE_GROUP_TYPE = 'OS::Heat::ResourceGroup'

#: The resource name used for package updates
UPDATE_RESOURCE_NAME = 'UpdateDeployment'

#: The default timeout to pass to Heat stacks
STACK_TIMEOUT_DEFAULT = 240

#: The default name to use for a plan container
DEFAULT_CONTAINER_NAME = 'overcloud'

#: The path to the tripleo heat templates installed on the undercloud
DEFAULT_TEMPLATES_PATH = '/usr/share/openstack-tripleo-heat-templates/'

# The path to the tripleo validations installed on the undercloud
DEFAULT_VALIDATIONS_PATH = \
    '/usr/share/openstack-tripleo-validations/validations/'

# TRIPLEO_META_USAGE_KEY is inserted into metadata for containers created in
# Swift via SwiftPlanStorageBackend to identify them from other containers
TRIPLEO_META_USAGE_KEY = 'x-container-meta-usage-tripleo'

# OBJECT_META_KEY_PREFIX is used to prefix Swift metadata keys per object
# in SwiftPlanStorageBackend
OBJECT_META_KEY_PREFIX = 'x-object-meta-'

#: List of names of parameters that contain passwords
PASSWORD_PARAMETER_NAMES = (
    'AdminPassword',
    'AdminToken',
    'AodhPassword',
    'BarbicanPassword',
    'CeilometerMeteringSecret',
    'CeilometerPassword',
    'CephAdminKey',
    'CephClientKey',
    'CephClusterFSID',
    'CephMonKey',
    'CephRgwKey',
    'CinderPassword',
    'GlancePassword',
    'GnocchiPassword',
    'HAProxyStatsPassword',
    'HeatPassword',
    'HeatStackDomainAdminPassword',
    'IronicPassword',
    'KeystoneCredential0',
    'KeystoneCredential1',
    'ManilaPassword',
    'MistralPassword',
    'MysqlClustercheckPassword',
    'NeutronMetadataProxySharedSecret',
    'NeutronPassword',
    'NovaPassword',
    'RabbitPassword',
    'RedisPassword',
    'SaharaPassword',
    'SnmpdReadonlyUserPassword',
    'SwiftHashSuffix',
    'SwiftPassword',
    'TrovePassword',
    'ZaqarPassword',
)
