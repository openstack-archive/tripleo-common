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
# upgrades workflow. Those roles that have disable_upgrade_deployment set to
# true will have had a /root/tripleo_upgrade_node.sh script delivered during
# the composable ansible upgrade steps. This tripleo_upgrade_node.sh is then
# invoked over ssh by the operator using the simple utility delivered in this
# file. See -h for options.
#
set -eu
set -o pipefail
SCRIPT_NAME=$(basename $0)

#can make the upgrade script overridable (if a different target will be used)
UPGRADE_SCRIPT=${UPGRADE_SCRIPT:-/root/tripleo_upgrade_node.sh}
#allow override incase the ssh user is not 'heat-admin' - must be able to sudo
UPGRADE_NODE_USER_DEFAULT="heat-admin"
UPGRADE_NODE_USER=${UPGRADE_NODE_USER:-$UPGRADE_NODE_USER_DEFAULT}
UPGRADE_NODE=""
QUERY_NODE=""
HOSTNAME=""
IP_ADDR=""
INVENTORY=""
ANSIBLE_OPTS="" # e.g. "--skip-tags validation"
function show_options {
    echo "Usage: $SCRIPT_NAME"
    echo
    echo "Options:"
    echo "  -h|--help                  -- print this help."
    echo "  -u|--upgrade <nova node>   -- nova node name or id or ctlplane IP"
    echo "                                to upgrade"
    echo "  -q|--query <nova node>     -- check if the node is ACTIVE and tail"
    echo "                                yum.log for any package update info"
    echo "  -I|--inventory <path>      -- use the specified tripleo ansible "
    echo "                                inventory (yaml format)"
    echo "  -O|--ansible-opts \"opts\"   -- specify extra options to be passed "
    echo "                                to ansible-playbook e.g. \"-vvv\" or "
    echo "                                \"-vvv --skip-tags validation\""
    echo "  -U|--overcloud-user <name> -- the user with which to ssh to the"
    echo "                                target upgrade node - defaults to"
    echo "                                $UPGRADE_NODE_USER_DEFAULT"
    echo
    echo "Invoke the /root/tripleo_upgrade_node.sh script on roles that have"
    echo "the 'disable_upgrade_deployment' flag set true and then download and"
    echo "execute the upgrade and deployment steps ansible playbooks."
    echo
    echo "The tripleo_upgrade_node.sh is delivered to the 'disable_upgrade_deployment'"
    echo "nodes, when you execute the composable upgrade steps on the "
    echo "controlplane nodes (i.e. the first step of the upgrade process). "
    echo
    echo "This utility is then used by the operator to invoke the upgrade workflow"
    echo "by named node (nova name or uuid) on the 'disable_upgrade_deployment'"
    echo "nodes. You can use the nova UUID, name or an IP address on the provisioning"
    echo "network (e.g. for split stack deployments)."
    echo
    echo "Logfiles are generated in the"
    echo "current working directory by node name/UUID/IP as appropriate."
    echo
    echo "Example invocations:"
    echo
    echo "    upgrade-non-controller.sh --upgrade overcloud-compute-0 "
    echo "    upgrade-non-controller.sh -u 734eea90-087b-4f12-9cd9-4807da83ea78 "
    echo "    upgrade-non-controller.sh -u 192.168.24.15 "
    echo "    upgrade-non-controller.sh -U stack -u 192.168.24.15 "
    echo "    upgrade-non-controller.sh -U stack -u 192.168.24.16 \ "
    echo "                              -I /home/stack/tripleo-ansible-inventory.yaml"
    echo "    upgrade-non-controller.sh -U stack -u 192.168.24.16 \ "
    echo "                              -I /home/stack/tripleo-ansible-inventory.yaml \ "
    echo "                              -O \"-vvv --skip-tags validation\" "
    echo
    echo "You can run on multiple nodes in parallel: "

    echo "    for i in \$(seq 0 2); do "
    echo "      upgrade-non-controller.sh --upgrade overcloud-compute-\$i &"
    echo "      # Remove the '&' above to have these upgrade in sequence"
    echo "    done"
    echo
    exit $1
}

TEMP=`getopt -o h,u:,q:,U:,I:,O: -l help,upgrade:,query:,overcloud-user:,inventory:,ansible-opts: -n $SCRIPT_NAME -- "$@"`

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
        -q | --query ) QUERY_NODE="$2" ; shift 2 ;;
        -U | --overcloud-user ) UPGRADE_NODE_USER="$2"; shift 2;;
        -I | --inventory ) INVENTORY="$2"; shift 2;;
        -O | --ansible-opts ) ANSIBLE_OPTS="$2"; shift 2;;
        -- ) shift ; break ;;
        * ) echo "Error: unsupported option $1." ; exit 1 ;;
    esac
done

LOGFILE="$SCRIPT_NAME"-$UPGRADE_NODE$QUERY_NODE
function log {
  echo "`date` $SCRIPT_NAME $1" 2>&1 | tee -a  $LOGFILE
}

if [[ -n $UPGRADE_NODE$QUERY_NODE ]]; then
    log "Logging to $LOGFILE"
fi

function reset_hostname_ip {
    HOSTNAME=""
    IP_ADDR=""
}

# find_node_by_name_id_or_ip expects one parameter that is the nova name,
# uuid or cltplane IP address of the node we want to upgrade.
# The function will try and determine the hostname and (ctlplane) IP address
# for that node and assign these values to the global HOSTNAME and IP_ADDR.
# These variables are thus reset at the outset.
function find_node_by_name_id_or_ip {
  reset_hostname_ip
  name_id_or_ip=$1
  # First try as a nova node name or UUID. Could also be an IP (split stack)
  set +e # dont want to fail if nova or ping does below
  nova_name=$(openstack server show $name_id_or_ip -f value -c name)
  if [[ -n $nova_name ]]; then
    set -e
    HOSTNAME=$nova_name
    addr_string=$(openstack server show $name_id_or_ip -f value -c addresses)
    IP_ADDR=${addr_string#*=} # remove the ctlpane from  ctlplane=192.168.24.11
    log "nova node $HOSTNAME found with IP $IP_ADDR "
  else
    log "$name_id_or_ip not known to nova. Trying it as an IP address"
    if ping -c1 $name_id_or_ip ; then
        set -e
        HOSTNAME=$(ssh $UPGRADE_NODE_USER@$name_id_or_ip hostname)
        IP_ADDR=$name_id_or_ip
        log "node $HOSTNAME found with address $IP_ADDR "
    else
        set -e
        log "ERROR $name_id_or_ip not known to nova or not responding to ping if it is an IP address. Exiting"
        exit 1
    fi
  fi
  set -e
}

# Generate static tripleo ansible inventory. This is mainly to deal with different
# ssh user for the ansible playbooks, e.g. in a split stack environment.
# $1 is the path for to write the tripleo-ansible-inventory to
function get_static_inventory {
  local config_dir=$1
  if [ -d "$config_dir" ] ;then
    local inventory_args=" --static-yaml-inventory $config_dir/tripleo-ansible-inventory.yaml"
    if [[ $UPGRADE_NODE_USER != $UPGRADE_NODE_USER_DEFAULT ]]; then
      inventory_args+=" --ansible_ssh_user $UPGRADE_NODE_USER"
    fi
    log "Generating static tripleo-ansible-inventory with these args: $inventory_args"
    /usr/bin/tripleo-ansible-inventory $inventory_args
  else
    log "ERROR can't generate tripleo-ansible-inventory - cannot find $config_dir"
    exit 1
  fi
}

function run_ansible_playbook {
    local playbook=$UPGRADE_NODE/$1
    full_args=" -b --limit $HOSTNAME --inventory $INVENTORY $ANSIBLE_OPTS $playbook"
    log "Running ansible-playbook with $full_args"
    ansible-playbook $full_args 2>&1 | tee -a  $LOGFILE
}

if [ -n "$UPGRADE_NODE" ]; then
  find_node_by_name_id_or_ip $UPGRADE_NODE
  log "Executing $UPGRADE_SCRIPT on $IP_ADDR"
  ssh $UPGRADE_NODE_USER@$IP_ADDR sudo $UPGRADE_SCRIPT 2>&1 | tee -a $LOGFILE
  log "Clearing any existing dir $UPGRADE_NODE and downloading config"
  rm -rf $UPGRADE_NODE
  openstack overcloud config download --config-dir "$UPGRADE_NODE"
  config_dir=$(ls -1 $UPGRADE_NODE)
  if [ -z "$INVENTORY" ]; then
    get_static_inventory $UPGRADE_NODE/$config_dir
    INVENTORY="$UPGRADE_NODE/$config_dir/tripleo-ansible-inventory.yaml"
  fi
  for book in upgrade_steps_playbook.yaml deploy_steps_playbook.yaml ; do
    run_ansible_playbook $config_dir/$book
  done
fi

if [ -n "$QUERY_NODE" ]; then
  # check node exists, check for upgrade script
  find_node_by_name_id_or_ip $QUERY_NODE
  log "We can't remotely tell if the upgrade has run on $QUERY_NODE."
  log "We can check for package updates... trying to tail yum.log on $QUERY_NODE:"
  ssh $UPGRADE_NODE_USER@$IP_ADDR "sudo tail /var/log/yum.log" 2>&1 | tee -a $LOGFILE
fi
