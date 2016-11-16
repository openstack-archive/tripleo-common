#!/bin/bash

set -ex

# Doing this in a separate script lets us do it step by step with a single docker layer.

if [ -n "$OPENSTACK_RELEASE" ]; then
    # Install specified OpenStack release
    yum -y install http://rdoproject.org/repos/openstack-$OPENSTACK_RELEASE/rdo-release-$OPENSTACK_RELEASE.rpm
else
    # Install from master
    curl -L -o /etc/yum.repos.d/delorean.repo \
        http://buildlogs.centos.org/centos/7/cloud/x86_64/rdo-trunk-master-tripleo/delorean.repo
    curl -L -o /etc/yum.repos.d/delorean-current.repo \
        http://trunk.rdoproject.org/centos7/current/delorean.repo
    sed -i 's/\[delorean\]/\[delorean-current\]/' /etc/yum.repos.d/delorean-current.repo
    cat << EOF >> /etc/yum.repos.d/delorean-current.repo

includepkgs=diskimage-builder,instack,instack-undercloud,os-apply-config,os-cloud-config,os-collect-config,os-net-config,os-refresh-config,python-tripleoclient,tripleo-common,openstack-tripleo-heat-templates,openstack-tripleo-image-elements,openstack-tripleo,openstack-tripleo-puppet-elements,openstack-puppet-modules
EOF

    curl -L -o /etc/yum.repos.d/delorean-deps.repo \
        http://trunk.rdoproject.org/centos7/delorean-deps.repo

    yum -y install yum-plugin-priorities
fi

yum update -y

# Install required packages
yum install -y \
        file \
        initscripts \
        jq \
        openstack-puppet-modules \
        openstack-tripleo-image-elements \
        openstack-tripleo-puppet-elements \
        openvswitch \
        os-net-config \
        python-heat-agent-apply-config \
        python-heat-agent-hiera \
        python-heat-agent-puppet \
        python-ipaddr \
        python2-oslo-log

# NOTE(flaper87): openstack packages
# We need these packages just to install the config files.
# Instead of installing the entire package, we'll extract the
# config files from the RPM and put them in place. This step will
# save us ~500 MB in the final size of the image.
yum install -y --downloadonly --downloaddir=/tmp/packages \
        libvirt-daemon-config-nwfilter \
        libvirt-daemon-kvm \
        openstack-ceilometer-compute \
        openstack-neutron \
        openstack-neutron-ml2 \
        openstack-neutron-openvswitch \
        openstack-nova-common \
        openstack-nova-compute \
        python-nova

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

# Install puppet modules
mkdir -p /etc/puppet/modules
ln -sf /usr/share/openstack-puppet/modules/* /etc/puppet/modules/

# And puppet hiera
mkdir -p /usr/libexec/os-apply-config/templates/etc/puppet
ln -sf /usr/share/tripleo-puppet-elements/hiera/os-apply-config/etc/puppet/hiera.yaml \
    /usr/libexec/os-apply-config/templates/etc/puppet/
ln -sf /etc/puppet/hiera.yaml /etc/hiera.yaml

# Configure os-*
ln -sf /usr/share/tripleo-puppet-elements/hiera/os-refresh-config/configure.d/40-hiera-datafiles \
    /usr/libexec/os-refresh-config/configure.d/
mkdir -p /usr/libexec/os-refresh-config/post-configure.d
ln -sf /usr/share/tripleo-image-elements/os-refresh-config/os-refresh-config/post-configure.d/99-refresh-completed \
    /usr/libexec/os-refresh-config/post-configure.d/

mkdir -p /usr/libexec/os-apply-config/templates/etc/os-net-config/
ln -sf /usr/share/tripleo-image-elements/os-net-config/os-apply-config/etc/os-net-config/config.json \
    /usr/libexec/os-apply-config/templates/etc/os-net-config/

# Remove unnecessary packages
yum autoremove -y
yum clean all
