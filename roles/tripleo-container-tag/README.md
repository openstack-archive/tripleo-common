tripleo-container-tag
=====================

An Ansible role to tag Pacemaker-managed containers.

Requirements
------------

It requires Docker or Podman on the host, depending which container CLI
is used.

Role variables
--------------

- container_image: -- Name of the container image to tag.
- container_image_latest: -- Name of the tag.
- container_cli: -- Name of the Container CLI tool (default to docker).
- pull_image: -- Pulling or not the image passed in container_image variable ( default to true).

Example Playbook
----------------

Sample playbook to call the role:

  - name: Tag Pacemaker containers
    hosts: all
    roles:
      - tripleo-container-tag
    vars:
      container_image: haproxy
      container_image_latest: pcmklatest
      container_cli: docker

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
