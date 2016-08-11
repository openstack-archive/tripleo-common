#!/bin/bash
#set -x
# Copyright 2016 Red Hat, Inc.
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

#
# Utility script that will be invoked by the operator as part of the documented
# tripleo upgrades workflow at [FIXME(marios): update this].
# In short the upgrade scripts are delivered to the non-controller nodes as
# part of the automated (heat delivered) controller upgrade. These are then
# invoked from this script by the operator. See -h for options.
#
set -eu
set -o pipefail
SCRIPT_NAME=$(basename $0)

#can make the upgrade script overridable (if a different target will be used)
UPGRADE_SCRIPT=${UPGRADE_SCRIPT:-/root/tripleo_upgrade_node.sh}
#allow override incase the ssh user is not 'heat-admin' - must be able to sudo
UPGRADE_NODE_USER=${UPGRADE_NODE_USER:-"heat-admin"}
UPGRADE_NODE=""
QUERY_NODE=""
SCRIPT=""

function show_options {
    echo "Usage: $SCRIPT_NAME"
    echo
    echo "Options:"
    echo "  -h|--help                    -- print this help."
    echo "  -u|--upgrade <nova node>     -- nova node name or id to upgrade"
    echo "  -s|--script <absolute_path>  -- absolute path to the script you wish"
    echo "                                  to use for the upgrade"
    echo "  -q|--query <nova node>       -- determine if the node is ACTIVE and"
    echo "                                  has the upgrade script. Also, tail"
    echo "                                  yum.log for any package update info"
    echo
    echo "Invoke the tripleo upgrade script on non controller nodes as part of"
    echo " the tripleo upgrade workflow."
    echo
    exit $1
}

TEMP=`getopt -o h,u:,q:,s: -l help,upgrade:,query:,script: -n $SCRIPT_NAME -- "$@"`

if [ $? != 0 ]; then
    echo "Terminating..." >&2
    exit 1
fi

# Note the quotes around `$TEMP': they are essential!
eval set -- "$TEMP"

while true ; do
    case "$1" in
        -h | --help ) show_options 0 >&2;;
        -u | --upgrade ) UPGRADE_NODE="$2" ; shift 2 ;;
        -s | --script ) SCRIPT="$2"; shift 2 ;;
        -q | --query ) QUERY_NODE="$2" ; shift 2 ;;
        -- ) shift ; break ;;
        * ) echo "Error: unsupported option $1." ; exit 1 ;;
    esac
done

function log {
  echo "`date` $SCRIPT_NAME $1"
}

function find_nova_node_by_name_or_id {
  name_or_id=$1
  node_status=$(openstack server show $name_or_id -f value -c status)
  if ! [[ $node_status == "ACTIVE" ]]; then
    log "ERROR: node $name_or_id not found to be ACTIVE. Current status is $node_status"
    exit 1
  fi
  log "nova node $name_or_id found with status $node_status"
}

function confirm_script_on_node {
  name_or_id=$1
  node_ip=$(nova show $name_or_id | grep "ctlplane network" | awk '{print $5}')
  log "checking for upgrade script $UPGRADE_SCRIPT on node $name_or_id ($node_ip)"
  results=$(ssh $UPGRADE_NODE_USER@$node_ip "sudo ls -l $UPGRADE_SCRIPT")
  log "upgrade script $UPGRADE_SCRIPT found on node $name_or_id ($node_ip)"
}

function deliver_script {
  script=$1
  node=$2
  node_ip=$(nova show $node | grep "ctlplane network" | awk '{print $5}')
  file_name=$(echo ${script##*/})
  log "Sending upgrade script $script to $node_ip as $UPGRADE_NODE_USER"
  scp $script $UPGRADE_NODE_USER@$node_ip:/home/$UPGRADE_NODE_USER/$file_name
  log "Copying upgrade script to right location and setting permissions"
  ssh $UPGRADE_NODE_USER@$node_ip "sudo cp /home/$UPGRADE_NODE_USER/$file_name $UPGRADE_SCRIPT ; \
                           sudo chmod 755 $UPGRADE_SCRIPT ; "
}

if [ -n "$UPGRADE_NODE" ]; then
  find_nova_node_by_name_or_id $UPGRADE_NODE
  if  [ -n "$SCRIPT" ]; then
    deliver_script $SCRIPT $UPGRADE_NODE
  fi
  confirm_script_on_node $UPGRADE_NODE
  node_ip=$(nova show $UPGRADE_NODE | grep "ctlplane network" | awk '{print $5}')
  log "Executing $UPGRADE_SCRIPT on $node_ip"
  ssh $UPGRADE_NODE_USER@$node_ip sudo $UPGRADE_SCRIPT
fi

if [ -n "$QUERY_NODE" ]; then
  # check node exists, check for upgrade script
  find_nova_node_by_name_or_id $QUERY_NODE
  confirm_script_on_node $QUERY_NODE
  node_ip=$(nova show $QUERY_NODE | grep "ctlplane network" | awk '{print $5}')
  log "We can't remotely tell if the upgrade has run on $QUERY_NODE."
  log "We can check for package updates... trying to tail yum.log on $QUERY_NODE:"
  ssh $UPGRADE_NODE_USER@$node_ip "sudo tail /var/log/yum.log"
fi
