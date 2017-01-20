FROM centos:7
MAINTAINER "Jeff Peeler" <jpeeler@redhat.com>

ARG OPENSTACK_RELEASE
LABEL openstack_release=$OPENSTACK_RELEASE
ENV container docker
ENV DOCKER_HOST unix:///var/run/docker.sock

# Just use a script to configure the agent container.  This way we can
# Split up the operations and do it all in a single layer.
ADD configure_container.sh /tmp/
RUN /tmp/configure_container.sh && rm /tmp/configure_container.sh

# create volumes to share the host directories
VOLUME [ "/var/lib/cloud"]
VOLUME [ "/var/lib/heat-cfntools" ]

CMD /usr/bin/os-collect-config
