#!/bin/bash
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

##############################################################################
# tripleo.sh is a script to automate a TripleO setup. It's goals are to be
# used in aiding:
#
# - developer setups
# - CI
# - documentation generation (hopefully)
#
# It's not a new CLI, or end user facing wrapper around existing TripleO
# CLI's.
#
# tripleo.sh should never contain any "business" logic in it that is
# necessary for a successful deployment. It should instead just mirror the
# steps that we document for TripleO end users.
#
##############################################################################


set -eu
set -o pipefail

SCRIPT_NAME=${SCRIPT_NAME:-$(basename $0)}

function show_options {
    echo "Usage: $SCRIPT_NAME [options]"
    echo
    echo "Automates TripleO setup steps."
    echo
    echo "$SCRIPT_NAME is also configurable via environment variables, most of"
    echo "which are not exposed via cli args for simplicity. See the source"
    echo "for the set of environment variables that can be overridden."
    echo
    echo "Note that cli args always take precedence over environment"
    echo "variables."
    echo
    echo "Options:"
    echo "      --repo-setup         -- Perform repository setup."
    echo "      --delorean-setup     -- Install local delorean build environment."
    echo "      --delorean-build     -- Build a delorean package locally"
    echo "      --undercloud         -- Install the undercloud."
    echo "      --overcloud-images   -- Build and load overcloud images."
    echo "      --register-nodes     -- Register and configure nodes."
    echo "      --introspect-nodes   -- Introspect nodes."
    echo "      --flavors            -- Create flavors for deployment."
    echo "      --overcloud-deploy   -- Deploy an overcloud."
    echo "      --overcloud-delete   -- Delete the overcloud."
    echo "      --use-containers     -- Use a containerized compute node."
    echo "      --overcloud-pingtest -- Run a tenant vm, attach and ping floating IP."
    echo "      --all, -a            -- Run all of the above commands."
    echo "      -x                   -- enable tracing"
    echo "      --help, -h           -- Print this help message."
    echo
    exit 1
}

if [ ${#@} = 0 ]; then
    show_options
    exit 1
fi

TEMP=$(getopt -o ,h \
        -l,help,repo-setup,delorean-setup,delorean-build,undercloud,overcloud-images,register-nodes,introspect-nodes,flavors,overcloud-deploy,overcloud-delete,use-containers,overcloud-pingtest,all \
        -o,x,h,a \
        -n $SCRIPT_NAME -- "$@")

if [ $? != 0 ]; then
    show_options
    exit 1
fi

# Note the quotes around `$TEMP': they are essential!
eval set -- "$TEMP"

ALL=${ALL:-""}
STABLE_RELEASE=${STABLE_RELEASE:-}
CONTAINER_ARGS=${CONTAINER_ARGS:-"-e /usr/share/openstack-tripleo-heat-templates/environments/docker.yaml -e /usr/share/openstack-tripleo-heat-templates/environments/docker-network.yaml --libvirt-type=qemu"}
DELOREAN_REPO_FILE=${DELOREAN_REPO_FILE:-"delorean.repo"}
DELOREAN_REPO_URL=${DELOREAN_REPO_URL:-"\
    http://trunk.rdoproject.org/centos7/current-tripleo/"}
FLAVORS=${FLAVORS:-""}
DELOREAN_STABLE_REPO_URL=${DELOREAN_STABLE_REPO_URL:-"\
    https://trunk.rdoproject.org/centos7-$STABLE_RELEASE/current/"}
ATOMIC_URL=${ATOMIC_URL:-"https://download.fedoraproject.org/pub/fedora/linux/releases/22/Cloud/x86_64/Images/Fedora-Cloud-Atomic-22-20150521.x86_64.qcow2"}
INSTACKENV_JSON_PATH=${INSTACKENV_JSON_PATH:-"$HOME/instackenv.json"}
INTROSPECT_NODES=${INTROSPECT_NODES:-""}
REGISTER_NODES=${REGISTER_NODES:-""}
OVERCLOUD_DEPLOY=${OVERCLOUD_DEPLOY:-""}
OVERCLOUD_DELETE=${OVERCLOUD_DELETE:-""}
OVERCLOUD_DELETE_TIMEOUT=${OVERCLOUD_DELETE_TIMEOUT:-"300"}
OVERCLOUD_DEPLOY_ARGS=${OVERCLOUD_DEPLOY_ARGS:-""}
OVERCLOUD_IMAGES_PATH=${OVERCLOUD_IMAGES_PATH:-"$HOME"}
OVERCLOUD_IMAGES=${OVERCLOUD_IMAGES:-""}
OVERCLOUD_IMAGES_DIB_YUM_REPO_CONF=${OVERCLOUD_IMAGES_DIB_YUM_REPO_CONF:-"\
    /etc/yum.repos.d/delorean.repo \
    /etc/yum.repos.d/delorean-current.repo \
    /etc/yum.repos.d/delorean-deps.repo"}
OVERCLOUD_NAME=${OVERCLOUD_NAME:-"overcloud"}
OVERCLOUD_PINGTEST=${OVERCLOUD_PINGTEST:-""}
REPO_SETUP=${REPO_SETUP:-""}
DELOREAN_SETUP=${DELOREAN_SETUP:-""}
DELOREAN_BUILD=${DELOREAN_BUILD:-""}
STDERR=/dev/null
UNDERCLOUD=${UNDERCLOUD:-""}
UNDERCLOUD_CONF=${UNDERCLOUD_CONF:-"/usr/share/instack-undercloud/undercloud.conf.sample"}
TRIPLEO_ROOT=${TRIPLEO_ROOT:-$HOME/tripleo}
USE_CONTAINERS=${USE_CONTAINERS:-""}

# TODO: remove this when Image create in openstackclient supports the v2 API
export OS_IMAGE_API_VERSION=1

while true ; do
    case "$1" in
        --all|-a ) ALL="1"; shift 1;;
        --use-containers) USE_CONTAINERS="1"; shift 1;;
        --flavors) FLAVORS="1"; shift 1;;
        --introspect-nodes) INTROSPECT_NODES="1"; shift 1;;
        --register-nodes) REGISTER_NODES="1"; shift 1;;
        --overcloud-deploy) OVERCLOUD_DEPLOY="1"; shift 1;;
        --overcloud-delete) OVERCLOUD_DELETE="1"; shift 1;;
        --overcloud-images) OVERCLOUD_IMAGES="1"; shift 1;;
        --overcloud-pingtest) OVERCLOUD_PINGTEST="1"; shift 1;;
        --repo-setup) REPO_SETUP="1"; shift 1;;
        --delorean-setup) DELOREAN_SETUP="1"; shift 1;;
        --delorean-build) DELOREAN_BUILD="1"; shift 1;;
        --undercloud) UNDERCLOUD="1"; shift 1;;
        -x) set -x; STDERR=/dev/stderr; shift 1;;
        -h | --help) show_options 0;;
        --) shift ; break ;;
        *) echo "Error: unsupported option $1." ; exit 1 ;;
    esac
done


function log {
    echo "#################"
    echo -n "$SCRIPT_NAME -- "
    echo $@
    echo "#################"
}

function source_rc {
    if [ $1 = "stackrc" ] ; then cloud="Undercloud"; else cloud="Overcloud"; fi
    echo "You must source a $1 file for the $cloud."
    echo "Attempting to source $HOME/$1"
    source $HOME/$1
    echo "Done"
}

function stackrc_check {
    source_rc "stackrc"
}

function overcloudrc_check {
    source_rc "overcloudrc"
}

function repo_setup {

    log "Repository setup"

    # sets $TRIPLEO_OS_FAMILY and $TRIPLEO_OS_DISTRO
    source $(dirname ${BASH_SOURCE[0]:-$0})/set-os-type

    if [ "$TRIPLEO_OS_DISTRO" = "centos" ]; then
        # Enable epel
        rpm -q epel-release || sudo yum -y install epel-release
    fi

    if [ -z "$STABLE_RELEASE" ]; then
        # Enable the Delorean Deps repository
        sudo curl -o /etc/yum.repos.d/delorean-deps.repo http://trunk.rdoproject.org/centos7/delorean-deps.repo
        sudo sed -i -e 's%priority=.*%priority=30%' /etc/yum.repos.d/delorean-deps.repo

        # Enable last known good RDO Trunk Delorean repository
        sudo curl -o /etc/yum.repos.d/delorean.repo $DELOREAN_REPO_URL/$DELOREAN_REPO_FILE
        sudo sed -i -e 's%priority=.*%priority=20%' /etc/yum.repos.d/delorean.repo

        # Enable latest RDO Trunk Delorean repository
        sudo curl -o /etc/yum.repos.d/delorean-current.repo http://trunk.rdoproject.org/centos7/current/delorean.repo
        sudo sed -i -e 's%priority=.*%priority=10%' /etc/yum.repos.d/delorean-current.repo
        sudo sed -i 's/\[delorean\]/\[delorean-current\]/' /etc/yum.repos.d/delorean-current.repo
        sudo /bin/bash -c "cat <<-EOF>>/etc/yum.repos.d/delorean-current.repo

includepkgs=diskimage-builder,instack,instack-undercloud,os-apply-config,os-cloud-config,os-collect-config,os-net-config,os-refresh-config,python-tripleoclient,tripleo-common,openstack-tripleo-heat-templates,openstack-tripleo-image-elements,openstack-tripleo,openstack-tripleo-puppet-elements
EOF"
    else
        # Enable the Delorean Deps repository
        sudo curl -o /etc/yum.repos.d/delorean-deps.repo http://trunk.rdoproject.org/centos7-$STABLE_RELEASE/delorean-deps.repo
        sudo sed -i -e 's%priority=.*%priority=30%' /etc/yum.repos.d/delorean-deps.repo

        # Enable delorean current for the stable version
        sudo curl -o /etc/yum.repos.d/delorean.repo $DELOREAN_STABLE_REPO_URL/$DELOREAN_REPO_FILE
        sudo sed -i -e 's%priority=.*%priority=20%' /etc/yum.repos.d/delorean.repo

        # Create empty delorean-current for dib image building
        sudo sh -c '> /etc/yum.repos.d/delorean-current.repo'
    fi

    # Install the yum-plugin-priorities package so that the Delorean repository
    # takes precedence over the main RDO repositories.
    sudo yum -y install yum-plugin-priorities

    log "Repository setup - DONE."

}

function delorean_setup {

    log "Delorean setup"

    # Install delorean as per combination of toci-instack and delorean docs
    sudo yum install -y createrepo git mock python-virtualenv rpm-build yum-plugin-priorities yum-utils

    # Add the current user to the mock group
    sudo usermod -G mock -a $(id -nu)

    mkdir -p $TRIPLEO_ROOT
    [ -d $TRIPLEO_ROOT/delorean ] || git clone https://github.com/openstack-packages/delorean.git $TRIPLEO_ROOT/delorean

    pushd $TRIPLEO_ROOT/delorean

    sudo rm -rf data commits.sqlite
    mkdir -p data

    sed -i -e "s%reponame=.*%reponame=delorean-ci%" projects.ini
    sed -i -e "s%target=.*%target=centos%" projects.ini

    # Remove the rpm install test to speed up delorean (our ci test will to this)
    # TODO: add an option for this in delorean
    sed -i -e 's%.*installed.*%touch $OUTPUT_DIRECTORY/installed%' scripts/build_rpm.sh

    virtualenv venv
    ./venv/bin/pip install -r requirements.txt
    ./venv/bin/python setup.py install

    popd
    log "Delorean setup - DONE."
}

function delorean_build {

    log "Delorean build"

    export PATH=/sbin:/usr/sbin:$PATH
    source $(dirname ${BASH_SOURCE[0]:-$0})/common_functions.sh

    pushd $TRIPLEO_ROOT/delorean

    if [ -z "$STABLE_RELEASE" ]; then
        sed -i -e "s%baseurl=.*%baseurl=https://trunk.rdoproject.org/centos7%" projects.ini
        sed -i -e "s%distro=.*%distro=rpm-master%" projects.ini
        sed -i -e "s%source=.*%source=master%" projects.ini
    else
        sed -i -e "s%baseurl=.*%baseurl=https://trunk.rdoproject.org/centos7-$STABLE_RELEASE%" projects.ini
        sed -i -e "s%distro=.*%distro=rpm-$STABLE_RELEASE%" projects.ini
        sed -i -e "s%source=.*%source=stable/$STABLE_RELEASE%" projects.ini
    fi

    sudo rm -rf data commits.sqlite
    mkdir -p data

    # build packages
    # loop through each of the projects listed in DELOREAN_BUILD_REFS, if it is a project we
    # are capable of building an rpm for then build it.
    # e.g. DELOREAN_BUILD_REFS="openstack/cinder openstack/heat etc.."
    for PROJ in $DELOREAN_BUILD_REFS ; do
        log "Building $PROJ"

        PROJ=$(filterref $PROJ)

        # Clone the repo if it doesn't yet exist
        if [ ! -d $TRIPLEO_ROOT/$PROJ ]; then
            git clone https://github.com/openstack/$PROJ.git $TRIPLEO_ROOT/$PROJ
            if [ ! -z "$STABLE_RELEASE" ]; then
                pushd $TRIPLEO_ROOT/$PROJ
                git checkout -b stable/$STABLE_RELEASE origin/stable/$STABLE_RELEASE
                popd
            fi
        fi

        MAPPED_PROJ=$(./venv/bin/python scripts/map-project-name $PROJ || true)
        [ -e data/$MAPPED_PROJ ] && continue
        cp -r $TRIPLEO_ROOT/$PROJ data/$MAPPED_PROJ
        pushd data/$MAPPED_PROJ
        GITHASH=$(git rev-parse HEAD)

        # Set the branches delorean reads to the same git hash as PROJ has left for us
        for BRANCH in master origin/master stable/liberty origin/stable/liberty; do
            git checkout -b $BRANCH || git checkout $BRANCH
            git reset --hard $GITHASH
        done
        popd

        # Using sudo to su a command as ourselves to run the command with a new login
        # to ensure the addition to the mock group has taken effect.
        sudo su $(id -nu) -c "./venv/bin/delorean --config-file projects.ini --head-only --package-name $MAPPED_PROJ --local --build-env DELOREAN_DEV=1 --build-env http_proxy=${http_proxy:-} --info-repo rdoinfo"
    done
    popd
    log "Delorean build - DONE."
}

function undercloud {

    log "Undercloud install"
    # We use puppet modules from source by default for master, for stable we
    # currently use a stable package (we may eventually want to use a
    # stable-puppet-modules element instead so we can set DIB_REPOREF.., etc)
    if [ -z "$STABLE_RELEASE" ]; then
        export DIB_INSTALLTYPE_puppet_modules=${DIB_INSTALLTYPE_puppet_modules:-source}
    else
        export DIB_INSTALLTYPE_puppet_modules=${DIB_INSTALLTYPE_puppet_modules:-}
    fi

    sudo yum install -y python-tripleoclient

    if [ ! -f ~/undercloud.conf ]; then
        cp -b -f $UNDERCLOUD_CONF ~/undercloud.conf
    else
        log "~/undercloud.conf  already exists, not overwriting"
    fi

    # Hostname check, add to /etc/hosts if needed
    if ! grep -E "^127.0.0.1\s*$HOSTNAME" /etc/hosts; then
        sudo /bin/bash -c "echo \"127.0.0.1 $HOSTNAME\" >> /etc/hosts"
    fi

    openstack undercloud install

    log "Undercloud install - DONE."

}

function overcloud_images {

    log "Overcloud images"
    log "Overcloud images saved in $OVERCLOUD_IMAGES_PATH"

    # We use puppet modules from source by default for master, for stable we
    # currently use a stable package (we may eventually want to use a
    # stable-puppet-modules element instead so we can set DIB_REPOREF.., etc)
    if [ -z "$STABLE_RELEASE" ]; then
        export DIB_INSTALLTYPE_puppet_modules=${DIB_INSTALLTYPE_puppet_modules:-source}
    else
        export DIB_INSTALLTYPE_puppet_modules=${DIB_INSTALLTYPE_puppet_modules:-}
    fi

    # (slagle) TODO: This needs to be fixed in python-tripleoclient or
    # diskimage-builder!
    # Ensure yum-plugin-priorities is installed
    echo -e '#!/bin/bash\nyum install -y yum-plugin-priorities' | sudo tee /usr/share/diskimage-builder/elements/yum/pre-install.d/99-tmphacks
    sudo chmod +x /usr/share/diskimage-builder/elements/yum/pre-install.d/99-tmphacks

    log "Overcloud images saved in $OVERCLOUD_IMAGES_PATH"
    pushd $OVERCLOUD_IMAGES_PATH
    DIB_YUM_REPO_CONF=$OVERCLOUD_IMAGES_DIB_YUM_REPO_CONF \
        openstack overcloud image build --all 2>&1 | \
        tee -a overcloud-image-build.log

    stackrc_check
    openstack overcloud image upload
    popd

    log "Overcloud images - DONE."

}

function register_nodes {

    log "Register nodes"

    if [ ! -f $INSTACKENV_JSON_PATH ]; then
        echo Could not find instackenv.json at $INSTACKENV_JSON_PATH
        echo Specify the path to instackenv.json with '$INSTACKENV_JSON_PATH'
        exit 1
    fi

    stackrc_check
    openstack baremetal import --json $INSTACKENV_JSON_PATH
    ironic node-list
    openstack baremetal configure boot

    log "Register nodes - DONE."

}

function introspect_nodes {

    log "Introspect nodes"

    stackrc_check
    openstack baremetal introspection bulk start

    log "Introspect nodes - DONE."

}


function flavors {

    log "Flavors"

    stackrc_check
    openstack flavor create --id auto --ram 4096 --disk 40 --vcpus 1 baremetal
    openstack flavor \
        set --property "capabilities:boot_option"="local" \
        baremetal

    log "Flavors - DONE."

}

function overcloud_deploy {

    log "Overcloud deploy"

    # Force use of --templates
    if [[ ! $OVERCLOUD_DEPLOY_ARGS =~ --templates ]]; then
        OVERCLOUD_DEPLOY_ARGS="$OVERCLOUD_DEPLOY_ARGS --templates"
    fi
    stackrc_check

    if [[ $USE_CONTAINERS == 1 ]]; then
        if ! glance image-list | grep  -q atomic-image; then
            wget $ATOMIC_URL
            glance image-create --name atomic-image --file `basename $ATOMIC_URL` --disk-format qcow2 --container-format bare
        fi
        OVERCLOUD_DEPLOY_ARGS="$OVERCLOUD_DEPLOY_ARGS $CONTAINER_ARGS"
    fi

    openstack overcloud deploy $OVERCLOUD_DEPLOY_ARGS
    log "Overcloud deployment started - DONE."

}

function overcloud_delete {

    log "Overcloud delete"

    stackrc_check

    # We delete the stack via heat, then wait for it to be deleted
    # This should be fairly quick, but we poll for OVERCLOUD_DELETE_TIMEOUT
    heat stack-delete "$OVERCLOUD_NAME"
    # Note, we need the ID, not the name, as stack-show will only return
    # soft-deleted stacks by ID (not name, as it may be reused)
    OVERCLOUD_ID=$(heat stack-list | grep "$OVERCLOUD_NAME" | awk '{print $2}')
    if $(tripleo wait_for -w $OVERCLOUD_DELETE_TIMEOUT -d 10 -s "DELETE_COMPLETE" -- "heat stack-show $OVERCLOUD_ID"); then
       log "Overcloud $OVERCLOUD_ID DELETE_COMPLETE"
    else
       log "Overcloud $OVERCLOUD_ID delete failed or timed out:"
       heat stack-show $OVERCLOUD_ID
       exit 1
    fi
}

function cleanup_pingtest {

    log "Overcloud pingtest, starting cleanup"
    overcloudrc_check
    heat stack-delete tenant-stack
    if $(tripleo wait_for -w 300 -d 10 -s "Stack not found" -- "heat stack-show tenant-stack" ); then
        log "Overcloud pingtest - deleted the tenant-stack heat stack"
    else
        log "Overcloud pingtest - time out waiting to delete tenant heat stack, please check manually"
    fi
    log "Overcloud pingtest - cleaning demo network 'nova' and 'pingtest_image' image"
    glance image-delete pingtest_image
    neutron net-delete nova
    log "Overcloud pingtest - DONE"
}


function overcloud_pingtest {

    log "Overcloud pingtest"
    exitval=0

    overcloudrc_check

    IMAGE_PATH=$OVERCLOUD_IMAGES_PATH/fedora-user.qcow2
    if [ ! -e $IMAGE_PATH ]; then
        log "Overcloud pingtest, trying to download Fedora image"
        curl -L -o $IMAGE_PATH http://cloud.fedoraproject.org/fedora-21.x86_64.qcow2
    fi
    log "Overcloud pingtest, uploading demo tenant image to glance"
    glance image-create --progress --name pingtest_image --is-public True --disk-format qcow2 --container-format bare --file $IMAGE_PATH

    log "Overcloud pingtest, creating demo tenant keypair and external network"
    if ! nova keypair-show default 2>/dev/null; then tripleo user-config; fi
    neutron net-create nova --shared --router:external=True --provider:network_type flat \
  --provider:physical_network datacentre
    FLOATING_IP_CIDR=${FLOATING_IP_CIDR:-"192.0.2.0/24"}
    FLOATING_IP_START=${FLOATING_IP_START:-"192.0.2.50"}
    FLOATING_IP_END=${FLOATING_IP_END:-"192.0.2.64"}
    EXTERNAL_NETWORK_GATEWAY=${EXTERNAL_NETWORK_GATEWAY:-"192.0.2.1"}
    neutron subnet-create --name ext-subnet --allocation-pool start=$FLOATING_IP_START,end=$FLOATING_IP_END --disable-dhcp --gateway $EXTERNAL_NETWORK_GATEWAY nova $FLOATING_IP_CIDR
    TENANT_PINGTEST_TEMPLATE=/usr/share/tripleo-common/tenantvm_floatingip.yaml
    if [ ! -e $TENANT_PINGTEST_TEMPLATE ]; then
        TENANT_PINGTEST_TEMPLATE=$(dirname `readlink -f -- $0`)/../templates/tenantvm_floatingip.yaml
    fi
    log "Overcloud pingtest, creating tenant-stack heat stack:"
    heat stack-create -f $TENANT_PINGTEST_TEMPLATE tenant-stack || exitval=1
    if tripleo wait_for -w 360 -d 10 -s "CREATE_COMPLETE" -- "heat stack-list | grep tenant-stack"; then
        log "Overcloud pingtest, heat stack CREATE_COMPLETE";

        vm1_ip=`heat output-show tenant-stack server1_public_ip -F raw`

        log "Overcloud pingtest, trying to ping the floating IPs $vm1_ip"

        if tripleo wait_for -w 360 -d 10 -s "bytes from $vm1_ip" -- "ping -c 1 $vm1_ip" ; then
            ping -c 1 $vm1_ip
            log "Overcloud pingtest, SUCCESS"
        else
            ping -c 1 $vm1_ip || :
            nova show Server1 || :
            nova service-list || :
            neutron agent-list || :
            nova console-log Server1 || :
            log "Overloud pingtest, FAIL"
            exitval=1
        fi
    else
        heat stack-show tenant-stack || :
        heat event-list tenant-stack || :
        heat resource-list -n 5 tenant-stack || :
        log "Overcloud pingtest, failed to create heat stack, trying cleanup"
        exitval=1
    fi
    cleanup_pingtest
    exit $exitval
}

if [ "$REPO_SETUP" = 1 ]; then
    repo_setup
fi

if [ "$DELOREAN_SETUP" = 1 ]; then
    delorean_setup
fi

if [ "$DELOREAN_BUILD" = 1 ]; then
    export DELOREAN_BUILD_REFS="${DELOREAN_BUILD_REFS:-$@}"
    if [ -z "$DELOREAN_BUILD_REFS" ]; then
        echo "Usage: $0 --delorean-build openstack/heat openstack/nova"
        exit 1
    fi
    delorean_build
fi

if [ "$UNDERCLOUD" = 1 ]; then
    undercloud
fi

if [ "$OVERCLOUD_IMAGES" = 1 ]; then
    overcloud_images
fi

if [ "$REGISTER_NODES" = 1 ]; then
    register_nodes
fi

if [ "$INTROSPECT_NODES" = 1 ]; then
    introspect_nodes
fi

if [ "$FLAVORS" = 1 ]; then
    flavors
fi

if [ "$OVERCLOUD_DEPLOY" = 1 ]; then
    overcloud_deploy
fi

if [ "$OVERCLOUD_DELETE" = 1 ]; then
    overcloud_delete
fi

if [[ "$USE_CONTAINERS" == 1 && "$OVERCLOUD_DEPLOY" != 1 ]]; then
    echo "Error: --overcloud-deploy flag is required with the flag --use-containers"
    exit 1
fi

if [ "$OVERCLOUD_PINGTEST" = 1 ]; then
    overcloud_pingtest
fi

if [ "$ALL" = 1 ]; then
    repo_setup
    undercloud
    overcloud_images
    register_nodes
    introspect_nodes
    flavors
    overcloud_deploy
fi
