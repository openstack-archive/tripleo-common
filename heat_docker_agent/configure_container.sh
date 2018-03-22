#!/bin/bash

set -ex

# Doing this in a separate script lets us do it step by step with a single docker layer.

if [ -n "$OPENSTACK_RELEASE" ]; then
    # Install specified OpenStack release
    yum -y install http://rdoproject.org/repos/openstack-$OPENSTACK_RELEASE/rdo-release-$OPENSTACK_RELEASE.rpm
else
    # The variables don't make a ton of sense this way, but they are
    # defined so that the rest of the trunk repository setup can be
    # exactly taken from tripleo.sh (after removing 'sudo'). This
    # should help avoid unwanted differences between containerized and
    # non-containerized trunk software sources.
    REPO_PREFIX=/etc/yum.repos.d
    DELOREAN_REPO_URL=https://trunk.rdoproject.org/centos7/current-tripleo/
    DELOREAN_REPO_FILE=delorean.repo

    # Enable the Delorean Deps repository
    curl -Lvo $REPO_PREFIX/delorean-deps.repo https://trunk.rdoproject.org/centos7/delorean-deps.repo
    sed -i -e 's%priority=.*%priority=30%' $REPO_PREFIX/delorean-deps.repo
    cat $REPO_PREFIX/delorean-deps.repo

    # Enable last known good RDO Trunk Delorean repository
    curl -Lvo $REPO_PREFIX/delorean.repo $DELOREAN_REPO_URL/$DELOREAN_REPO_FILE
    sed -i -e 's%priority=.*%priority=20%' $REPO_PREFIX/delorean.repo
    cat $REPO_PREFIX/delorean.repo

    # Enable latest RDO Trunk Delorean repository
    curl -Lvo $REPO_PREFIX/delorean-current.repo https://trunk.rdoproject.org/centos7/current/delorean.repo
    sed -i -e 's%priority=.*%priority=10%' $REPO_PREFIX/delorean-current.repo
    sed -i 's/\[delorean\]/\[delorean-current\]/' $REPO_PREFIX/delorean-current.repo
    /bin/bash -c "cat <<-EOF>>$REPO_PREFIX/delorean-current.repo

includepkgs=diskimage-builder,instack,instack-undercloud,os-apply-config,os-collect-config,os-net-config,os-refresh-config,python-tripleoclient,openstack-tripleo-common,openstack-tripleo-heat-templates,openstack-tripleo-image-elements,openstack-tripleo,openstack-tripleo-puppet-elements,openstack-tripleo-ui,puppet-*
EOF"
    cat $REPO_PREFIX/delorean-current.repo

    yum -y install yum-plugin-priorities
fi

yum update -y

# Install required packages
yum install -y \
        file \
        initscripts \
        jq \
        puppet-tripleo \
        openstack-tripleo-image-elements \
        openstack-tripleo-puppet-elements \
        openvswitch \
        os-net-config \
        dhclient \
        ethtool \
        python-heat-agent-* \
        python-ipaddr \
        python-memcached \
        python2-oslo-log \
        MySQL-python

# NOTE(flaper87): openstack packages
# We need these packages just to install the config files.
# Instead of installing the entire package, we'll extract the
# config files from the RPM and put them in place. This step will
# save us ~500 MB in the final size of the image.
yum install -y --downloadonly --downloaddir=/tmp/packages \
        libvirt-daemon-config-nwfilter \
        libvirt-daemon-kvm \
        python-nova \
        openstack-*

CUR=$(pwd)
cd /tmp/packages
for package in $(ls *.rpm); do
    rpm2cpio $package | cpio -ivd ./etc/*

    if [ -d 'etc' ]; then
        cp -r etc/* /etc
        rm -Rf etc
    fi
done
cd $CUR && rm -Rf /tmp/packages

# Make libvirt work without virtlogd
sed -i -r "s/^[# ]*stdio_handler *=.+$/stdio_handler = \"file\"/" /etc/libvirt/qemu.conf

# Install puppet modules
mkdir -p /etc/puppet/modules
ln -sf /usr/share/openstack-puppet/modules/* /etc/puppet/modules/

# And puppet hiera
ln -sf /etc/puppet/hiera.yaml /etc/hiera.yaml

# Configure os-*
mkdir -p /usr/libexec/os-refresh-config/post-configure.d
ln -sf /usr/share/tripleo-image-elements/os-refresh-config/os-refresh-config/post-configure.d/99-refresh-completed \
    /usr/libexec/os-refresh-config/post-configure.d/

# Remove unnecessary packages
yum autoremove -y
yum clean all
