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

#: The default name to use for the container for validations
VALIDATIONS_CONTAINER_NAME = 'tripleo-validations'

#: The name of the plan subdirectory that holds custom validations
CUSTOM_VALIDATIONS_FOLDER = 'custom-validations'

#: The default key to use for updating parameters in plan environment.
DEFAULT_PLAN_ENV_KEY = 'parameter_defaults'

#: The path to the tripleo heat templates installed on the undercloud
DEFAULT_TEMPLATES_PATH = '/usr/share/openstack-tripleo-heat-templates/'

#: The path to the base directory of tripleo-validations
DEFAULT_VALIDATIONS_BASEDIR = "/usr/share/ansible"
DEFAULT_VALIDATIONS_LEGACY_BASEDIR = "/usr/share/openstack-tripleo-validations"

# The path to the tripleo validations installed on the undercloud
DEFAULT_VALIDATIONS_PATH = "{}/validation-playbooks/".format(
    DEFAULT_VALIDATIONS_BASEDIR)

# The path to the local CA certificate installed on the undercloud
LOCAL_CACERT_PATH = '/etc/pki/ca-trust/source/anchors/cm-local-ca.pem'

# TRIPLEO_META_USAGE_KEY is inserted into metadata for containers created in
# Swift via SwiftPlanStorageBackend to identify them from other containers
TRIPLEO_META_USAGE_KEY = 'x-container-meta-usage-tripleo'

# 60 minutes maximum to build the child layers at the same time.
BUILD_TIMEOUT = 3600

#: List of names of parameters that contain passwords
PASSWORD_PARAMETER_NAMES = (
    'AdminPassword',
    'AdminToken',
    'AodhPassword',
    'BarbicanPassword',
    'BarbicanSimpleCryptoKek',
    'CeilometerMeteringSecret',
    'CeilometerPassword',
    'CephClientKey',
    'CephClusterFSID',
    'CephManilaClientKey',
    'CephRgwKey',
    'CephGrafanaAdminPassword',
    'CephDashboardAdminPassword',
    'CinderPassword',
    'CongressPassword',
    'DesignatePassword',
    'DesignateRndcKey',
    'Ec2ApiPassword',
    'EtcdInitialClusterToken',
    'GlancePassword',
    'GnocchiPassword',
    'HAProxyStatsPassword',
    'HeatAuthEncryptionKey',
    'HeatPassword',
    'HeatStackDomainAdminPassword',
    'HorizonSecret',
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
    'MysqlRootPassword',
    'NeutronMetadataProxySharedSecret',
    'NeutronPassword',
    'NovaPassword',
    'NovajoinPassword',
    'MigrationSshKey',
    'OctaviaServerCertsKeyPassphrase',
    'OctaviaCaKeyPassphrase',
    'OctaviaHeartbeatKey',
    'OctaviaPassword',
    'PacemakerRemoteAuthkey',
    'PankoPassword',
    'PcsdPassword',
    'PlacementPassword',
    'RpcPassword',
    'NotifyPassword',
    'RabbitCookie',
    'RabbitPassword',
    'RedisPassword',
    'SaharaPassword',
    'SnmpdReadonlyUserPassword',
    'SwiftHashSuffix',
    'SwiftPassword',
    'ZaqarPassword',
)

# List of passwords that should not be rotated by default using the
# GeneratePasswordAction because they require some special handling
DO_NOT_ROTATE_LIST = (
    'BarbicanSimpleCryptoKek',
    'KeystoneCredential0',
    'KeystoneCredential1',
    'KeystoneFernetKey0',
    'KeystoneFernetKey1',
    'KeystoneFernetKeys',
    'CephClientKey',
    'CephClusterFSID',
    'CephManilaClientKey',
    'CephRgwKey',
    'HeatAuthEncryptionKey',
)

PLAN_NAME_PATTERN = '^[a-zA-Z0-9-]+$'

# The default version of the Identity API to set in overcloudrc.
DEFAULT_IDENTITY_API_VERSION = '3'

# The default version of the Compute API to set in overcloudrc.
DEFAULT_COMPUTE_API_VERSION = '2.latest'

# The default version of the Image API to set in overcloudrc.
DEFAULT_IMAGE_API_VERSION = '2'

# The default version of the Volume API to set in overcloudrc.
DEFAULT_VOLUME_API_VERSION = '3'

# The name of the file which holds the Mistral environment contents for plan
# import/export
PLAN_ENVIRONMENT = 'plan-environment.yaml'

# Name of the environment with merged parameters from CLI
USER_ENVIRONMENT = 'user-environment.yaml'

# The name of the file which holds container image default parameters
CONTAINER_DEFAULTS_ENVIRONMENT = ('environments/'
                                  'containers-default-parameters.yaml')

DEFAULT_DEPLOY_KERNEL_NAME = 'bm-deploy-kernel'

DEFAULT_DEPLOY_RAMDISK_NAME = 'bm-deploy-ramdisk'

# The name for the swift container to host the cache for tripleo
TRIPLEO_CACHE_CONTAINER = "__cache__"

TRIPLEO_UI_LOG_FILE_SIZE = 1e7  # 10MB
TRIPLEO_UI_LOG_FILENAME = 'tripleo-ui.logs'

API_NETWORK = 'InternalApi'
LEGACY_API_NETWORK = 'Internal'

# Default nested depth when recursing Heat stacks
NESTED_DEPTH = 7

# Resource name for deployment resources when using config download
TRIPLEO_DEPLOYMENT_RESOURCE = 'TripleODeployment'

# Resource name for network config resources when using config download
TRIPLEO_NETWORK_CONFIG_RESOURCE = 'NetworkConfig'

HOST_NETWORK = 'ctlplane'

DEFAULT_VLAN_ID = "1"

# The key is different in RoleConfig than in RoleData, so we need both so they
# are correctly found.
EXTERNAL_TASKS = ['external_deploy_tasks', 'external_deploy_steps_tasks']

ANSIBLE_ERRORS_FILE = 'ansible-errors.json'

DEPLOYMENT_STATUS_FILE = 'deployment_status.yaml'

MISTRAL_WORK_DIR = '/var/lib/mistral'

EXCLUSIVE_NEUTRON_DRIVERS = ['ovn', 'openvswitch']

DEFAULT_STEPS_MAX = 6

_PER_STEP_TASK_STRICTNESS = [False for i in range(DEFAULT_STEPS_MAX)]

PER_STEP_TASKS = {
    'upgrade_tasks': _PER_STEP_TASK_STRICTNESS,
    'deploy_steps_tasks': _PER_STEP_TASK_STRICTNESS,
    'update_tasks': _PER_STEP_TASK_STRICTNESS,
    'post_update_tasks': [False, False, False, False]
}

INVENTORY_NETWORK_CONFIG_FILE = 'inventory-network-config.yaml'

# Hard coded name in:
#   tripleo_ansible/ansible_plugins/modules/tripleo_ovn_mac_addresses.py
OVN_MAC_ADDR_NET_NAME = 'ovn_mac_addr_net'
