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

#: The name of custom roles network data file used when rendering j2 templates.
OVERCLOUD_J2_NETWORKS_NAME = "network_data.yaml"

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

#: The default name to use for the config files of the container
CONFIG_CONTAINER_NAME = 'overcloud-config'

#: The default key to use for updating parameters in plan environment.
DEFAULT_PLAN_ENV_KEY = 'parameter_defaults'

#: The path to the tripleo heat templates installed on the undercloud
DEFAULT_TEMPLATES_PATH = '/usr/share/openstack-tripleo-heat-templates/'

# The path to the tripleo validations installed on the undercloud
DEFAULT_VALIDATIONS_PATH = \
    '/usr/share/openstack-tripleo-validations/validations/'

# TRIPLEO_META_USAGE_KEY is inserted into metadata for containers created in
# Swift via SwiftPlanStorageBackend to identify them from other containers
TRIPLEO_META_USAGE_KEY = 'x-container-meta-usage-tripleo'

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
    'CephMdsKey',
    'CephManilaClientKey',
    'CephMonKey',
    'CephRgwKey',
    'CinderPassword',
    'CongressPassword',
    'Ec2ApiPassword',
    'EtcdInitialClusterToken',
    'GlancePassword',
    'GnocchiPassword',
    'HAProxyStatsPassword',
    'HeatPassword',
    'HeatStackDomainAdminPassword',
    'IronicPassword',
    'LibvirtTLSPassword',
    'KeystoneCredential0',
    'KeystoneCredential1',
    'KeystoneFernetKey0',
    'KeystoneFernetKey1',
    'KeystoneFernetKeys',
    'ManilaPassword',
    'MistralPassword',
    'MysqlClustercheckPassword',
    'NeutronMetadataProxySharedSecret',
    'NeutronPassword',
    'NovaPassword',
    'NovajoinPassword',
    'MigrationSshKey',
    'OctaviaHeartbeatKey',
    'OctaviaPassword',
    'PacemakerRemoteAuthkey',
    'PankoPassword',
    'RabbitPassword',
    'RedisPassword',
    'SaharaPassword',
    'SnmpdReadonlyUserPassword',
    'SwiftHashSuffix',
    'SwiftPassword',
    'TackerPassword',
    'TrovePassword',
    'ZaqarPassword',
)

PLAN_NAME_PATTERN = '^[a-zA-Z0-9-]+$'

# The default version of the Bare metal API to set in overcloudrc.
# 1.34 is the latest API version in Ironic Pike supported by ironicclient.
DEFAULT_BAREMETAL_API_VERSION = '1.34'

# The default version of the Image API to set in overcloudrc.
DEFAULT_IMAGE_API_VERSION = '2'

# The default version of the Volume API to set in overcloudrc.
DEFAULT_VOLUME_API_VERSION = '3'

# The name of the file which holds the Mistral environment contents for plan
# import/export
PLAN_ENVIRONMENT = 'plan-environment.yaml'

# The name of the file which holds container image default parameters
CONTAINER_DEFAULTS_ENVIRONMENT = ('environments/'
                                  'containers-default-parameters.yaml')

DEFAULT_DEPLOY_KERNEL_NAME = 'bm-deploy-kernel'

DEFAULT_DEPLOY_RAMDISK_NAME = 'bm-deploy-ramdisk'

# The name for the swift container to host the cache for tripleo
TRIPLEO_CACHE_CONTAINER = "__cache__"

TRIPLEO_UI_LOG_FILE_SIZE = 1e7  # 10MB
TRIPLEO_UI_LOG_FILENAME = 'tripleo-ui.logs'
