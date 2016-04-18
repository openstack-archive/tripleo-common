#!/bin/bash

# Doing this in a separate script lets us do it step by step with a single docker layer.

yum -y install http://rdoproject.org/repos/openstack-liberty/rdo-release-liberty.rpm
yum update -y \
    && yum clean all
yum install -y \
        initscripts \
        dhcp-client \
        ethtool \
        NetworkManager

# We shouldn't need python-zaqarclient here for os-collect-config.
# The rpm should pull it in but it's not doing that..
# Also note gcc and python-pip, python-devel, and libyaml-devel are
# required for docker-compose.  It would be nice to package that or use
# somethinge else.
yum install -y \
        openstack-tripleo-puppet-elements \
        openstack-tripleo-image-elements \
        openstack-heat-templates \
        openstack-puppet-modules \
        os-apply-config \
        os-collect-config \
        os-refresh-config \
        os-net-config \
        jq \
        python-zaqarclient \
        gcc \
        libyaml-devel \
        python-devel \
        python-pip \
        openvswitch \
        puppet \
        python-ipaddr

# openstack packages
yum install -y \
	openstack-ceilometer-compute \
	python-nova \
	openstack-nova-common \
	openstack-neutron \
	libvirt-daemon-config-nwfilter \
	libvirt-daemon-kvm \
	openstack-nova-compute \
	openstack-neutron-ml2 \
	openstack-neutron-openvswitch

# heat-config-docker-compose
# TODO: fix! yet another requirement for docker-compose
pip install dpath functools32
yum install -y \
        docker


pip install -U docker-compose

yum clean all


# Heat config setup.
mkdir -p /var/lib/heat-config/hooks

ln -sf /usr/share/openstack-heat-templates/software-config/elements/heat-config-puppet/install.d/hook-puppet.py \
/var/lib/heat-config/hooks/puppet

ln -sf /usr/share/openstack-heat-templates/software-config/elements/heat-config-script/install.d/hook-script.py \
/var/lib/heat-config/hooks/script

ln -sf /usr/share/openstack-heat-templates/software-config/elements/heat-config-docker-compose/install.d/hook-docker-compose.py \
/var/lib/heat-config/hooks/docker-compose

# Install puppet modules
mkdir -p /etc/puppet/modules
ln -sf /usr/share/openstack-puppet/modules/* /etc/puppet/modules/

# And puppet hiera
mkdir -p /usr/libexec/os-apply-config/templates/etc/puppet
ln -sf /usr/share/tripleo-puppet-elements/hiera/os-apply-config/etc/puppet/hiera.yaml /usr/libexec/os-apply-config/templates/etc/puppet/
ln -sf /etc/puppet/hiera.yaml /etc/hiera.yaml

# Configure os-*
mkdir -p /usr/libexec/os-refresh-config/configure.d
ln -sf /usr/share/tripleo-image-elements/os-apply-config/os-refresh-config/configure.d/20-os-apply-config \
/usr/libexec/os-refresh-config/configure.d/
ln -sf /usr/share/openstack-heat-templates/software-config/elements/heat-config-docker-compose/os-refresh-config/configure.d/50-heat-config-docker-compose \
/usr/libexec/os-refresh-config/configure.d/
ln -sf /usr/share/openstack-heat-templates/software-config/elements/heat-config/os-refresh-config/configure.d/55-heat-config \
/usr/libexec/os-refresh-config/configure.d/
ln -sf /usr/share/tripleo-puppet-elements/hiera/os-refresh-config/configure.d/40-hiera-datafiles \
/usr/libexec/os-refresh-config/configure.d/
mkdir -p /usr/libexec/os-refresh-config/post-configure.d
ln -sf /usr/share/tripleo-image-elements/os-refresh-config/os-refresh-config/post-configure.d/99-refresh-completed \
/usr/libexec/os-refresh-config/post-configure.d/

mkdir -p /usr/libexec/os-apply-config/templates/var/run/heat-config
echo "{{deployments}}" > /usr/libexec/os-apply-config/templates/var/run/heat-config/heat-config

ln -sf /usr/share/openstack-heat-templates/software-config/elements/heat-config/bin/heat-config-notify \
/usr/local/bin/

mkdir -p /usr/libexec/os-apply-config/templates/etc/os-net-config/
ln -sf /usr/share/tripleo-image-elements/os-net-config/os-apply-config/etc/os-net-config/config.json \
/usr/libexec/os-apply-config/templates/etc/os-net-config/

mkdir -p /usr/libexec/os-apply-config/templates/etc/
ln -sf /usr/share/tripleo-image-elements/os-collect-config/os-apply-config/etc/os-collect-config.conf \
/usr/libexec/os-apply-config/templates/etc

