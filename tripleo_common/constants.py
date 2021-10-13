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


#: The resource name used for package updates
UPDATE_RESOURCE_NAME = 'UpdateDeployment'

#: The default timeout to pass to Heat stacks
STACK_TIMEOUT_DEFAULT = 240

#: The default name to use for a plan container
DEFAULT_CONTAINER_NAME = 'overcloud'

#: The default name to use for the config files of the container
CONFIG_CONTAINER_NAME = 'overcloud-config'

#: The path to the base directory of tripleo-validations
DEFAULT_VALIDATIONS_BASEDIR = "/usr/share/ansible"

# 60 minutes maximum to build the child layers at the same time.
BUILD_TIMEOUT = 3600

#: List of names of parameters that contain passwords
PASSWORD_PARAMETER_NAMES = (
    'AdminPassword',
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
    'DesignatePassword',
    'DesignateRndcKey',
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
    'KeystonePassword',
    'ManilaPassword',
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
    'PcsdPassword',
    'PlacementPassword',
    'RpcPassword',
    'NotifyPassword',
    'RabbitCookie',
    'RabbitPassword',
    'RedisPassword',
    'SnmpdReadonlyUserPassword',
    'SwiftHashSuffix',
    'SwiftPassword',
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

# The default version of the Identity API to set in overcloudrc.
DEFAULT_IDENTITY_API_VERSION = '3'

# The default version of the Compute API to set in overcloudrc.
DEFAULT_COMPUTE_API_VERSION = '2.latest'

# The default version of the Image API to set in overcloudrc.
DEFAULT_IMAGE_API_VERSION = '2'

# The default version of the Volume API to set in overcloudrc.
DEFAULT_VOLUME_API_VERSION = '3'

# Default nested depth when recursing Heat stacks
NESTED_DEPTH = 7

# Resource name for deployment resources when using config download
TRIPLEO_DEPLOYMENT_RESOURCE = 'TripleODeployment'

HOST_NETWORK = 'ctlplane'

DEFAULT_VLAN_ID = "1"

# The key is different in RoleConfig than in RoleData, so we need both so they
# are correctly found.
EXTERNAL_TASKS = ['external_deploy_tasks', 'external_deploy_steps_tasks']

ANSIBLE_ERRORS_FILE = 'ansible-errors.json'

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
