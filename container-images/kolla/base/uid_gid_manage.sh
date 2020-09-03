#!/bin/bash
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
#
# This script maintains compatibility when upgrading kolla images to the
# TCIB images. To allow containers reading configuration files, we need to
# maintain the same UIDs/GIDs for now until we update file permissions during
# update/upgrade tasks.
#
# Usage:
# ./uid_gid_manage.sh qemu nova
#
# Note: order of args is maintained during the creation.
#

set -o errexit
set -o xtrace

[ -z $1 ] && echo "Argument missing: name of user to create" && exit 1
_USERS_TO_CREATE=$@

declare -A _SUPPORTED_USERS
# This comes from kolla/common/config.py.
# Format: <username> <uid> <gid> <optional homedir> <optional comma-separated list of extra groups>
# Note: if homedir isn't specified, extra groups aren't supported
_SUPPORTED_USERS['aodh']='aodh 42402 42402 /var/lib/aodh kolla'
_SUPPORTED_USERS['barbican']='barbican 42403 42403 /var/lib/barbican kolla,nfast'
_SUPPORTED_USERS['ceilometer']='ceilometer 42405 42405 /var/lib/ceilometer kolla'
_SUPPORTED_USERS['cinder']='cinder 42407 42407 /var/lib/cinder kolla'
_SUPPORTED_USERS['collectd']='collectd 42409 42409 /var/lib/collectd kolla'
_SUPPORTED_USERS['designate']='designate 42411 42411 /var/lib/designate kolla'
_SUPPORTED_USERS['ec2api']='ec2api 42466 42466 /var/lib/ec2api kolla'
_SUPPORTED_USERS['etcd']='etcd 42413 42413 /var/lib/etcd kolla'
_SUPPORTED_USERS['glance']='glance 42415 42415 /var/lib/glance kolla'
_SUPPORTED_USERS['gnocchi']='gnocchi 42416 42416 /var/lib/gnocchi kolla'
_SUPPORTED_USERS['haproxy']='haproxy 42454 42454 /var/lib/haproxy kolla'
_SUPPORTED_USERS['heat']='heat 42418 42418 /var/lib/heat kolla'
_SUPPORTED_USERS['horizon']='horizon 42420 42420 /var/lib/horizon kolla'
_SUPPORTED_USERS['hugetlbfs']='hugetlbfs 42477 42477'
_SUPPORTED_USERS['ironic']='ironic 42422 42422 /var/lib/ironic kolla'
_SUPPORTED_USERS['ironic-inspector']='ironic-inspector 42461 42461 /var/lib/ironic-inspector kolla'
_SUPPORTED_USERS['keystone']='keystone 42425 42425 /var/lib/keystone kolla'
_SUPPORTED_USERS['kolla']='kolla 42400 42400'
_SUPPORTED_USERS['libvirt']='libvirt 42473 42473'
_SUPPORTED_USERS['manila']='manila 42429 42429 /var/lib/manila kolla'
_SUPPORTED_USERS['memcached']='memcached 42457 42457 /run/memcache kolla'
_SUPPORTED_USERS['mistral']='mistral 42430 42430 /var/lib/mistral kolla'
_SUPPORTED_USERS['mysql']='mysql 42434 42434 /var/lib/mysql kolla'
_SUPPORTED_USERS['neutron']='neutron 42435 42435 /var/lib/neutron kolla'
_SUPPORTED_USERS['nfast']='nfast 42481 42481'
_SUPPORTED_USERS['nova']='nova 42436 42436 /var/lib/nova qemu,libvirt,kolla'
_SUPPORTED_USERS['novajoin']='novajoin 42470 42470 /var/lib/novajoin kolla'
_SUPPORTED_USERS['octavia']='octavia 42437 42437 /var/lib/octavia kolla'
_SUPPORTED_USERS['openvswitch']='openvswitch 42476 42476'
_SUPPORTED_USERS['panko']='panko 42438 42438 /var/lib/panko ceilometer,kolla'
_SUPPORTED_USERS['placement']='placement 42482 42482 /var/lib/placement kolla'
_SUPPORTED_USERS['qdrouterd']='qdrouterd 42465 42465 /var/lib/qdrouterd kolla'
_SUPPORTED_USERS['qemu']='qemu 42427 42427'
_SUPPORTED_USERS['rabbitmq']='rabbitmq 42439 42439 /var/lib/rabbitmq kolla'
_SUPPORTED_USERS['redis']='redis 42460 42460 /run/redis kolla'
_SUPPORTED_USERS['swift']='swift 42445 42445 /var/lib/swift kolla'
_SUPPORTED_USERS['tempest']='tempest 42480 42480 /var/lib/tempest kolla'
_SUPPORTED_USERS['zaqar']='zaqar 42452 42452 /var/lib/zaqar kolla'

for _USER_TO_CREATE in $_USERS_TO_CREATE; do
    # Initialize computed args
    _EXTRA_GROUPS_ARG=
    _EXTRA_PERMS=
    _HOME_ARGS=

    _NAME=$(echo ${_SUPPORTED_USERS[$_USER_TO_CREATE]} | awk '{ print $1 }')
    _UID=$(echo ${_SUPPORTED_USERS[$_USER_TO_CREATE]} | awk '{ print $2 }')
    _GID=$(echo ${_SUPPORTED_USERS[$_USER_TO_CREATE]} | awk '{ print $3 }')
    _HOME_DIR=$(echo ${_SUPPORTED_USERS[$_USER_TO_CREATE]} | awk '{ print $4 }')
    _EXTRA_GROUPS=$(echo ${_SUPPORTED_USERS[$_USER_TO_CREATE]} | awk '{ print $5 }')

    # User was not found, we fail
    if [[ "$_NAME" != "$_USER_TO_CREATE" ]]; then
        echo "User ${_USER_TO_CREATE} was not found in the supported list"
        exit 1
    fi

    if [[ ! -z $_EXTRA_GROUPS ]]; then
        _EXTRA_GROUPS_ARG="--groups $_EXTRA_GROUPS"
    fi

    # Some users don't need a home directory
    if [[ -z $_HOME_DIR ]]; then
        _HOME_ARGS="-M"
    else
        _HOME_ARGS="-m --home $_HOME_DIR"
    fi

    if id -g $_NAME 2>/dev/null; then
        _GROUPADD_CMD="groupmod --gid $_GID $_NAME"
    else
        _GROUPADD_CMD="groupadd --gid $_GID $_NAME"
    fi

    if id $_NAME 2>/dev/null; then
        # -M argument doesn't exist with usermod
        if [[ -z $_HOME_DIR ]]; then
            _HOME_ARGS=
        # usermod doesn't guaranty the home directory permissions (best effort)
        else
            _EXTRA_PERMS="&& mkdir -p $_HOME_DIR && chown -R $_UID:$_GID $_HOME_DIR"
        fi
        # --append only exists with usermod
        [ ! -z $_EXTRA_GROUPS_ARG ] && _EXTRA_GROUPS_ARG="--append $_EXTRA_GROUPS_ARG"
        _USERADD_CMD="usermod ${_HOME_ARGS} --gid $_GID --uid $_UID ${_EXTRA_GROUPS_ARG} $_NAME ${_EXTRA_PERMS}"
    else
        _USERADD_CMD="useradd -l ${_HOME_ARGS} --shell /usr/sbin/nologin --uid $_UID --gid $_GID ${_EXTRA_GROUPS_ARG} $_NAME"
    fi
    eval $_GROUPADD_CMD
    eval $_USERADD_CMD
done
