tripleo-docker-rm
=================

An Ansible role to remove Docker containers when Podman is enabled.

Requirements
------------

It requires python-docker on the host.

Role variables
--------------

- container_cli: -- Name of the Container CLI tool (default to docker).
- containers_to_rm: -- List of containers to remove.

Example Playbook
----------------

Sample playbook to call the role:

  - name: Remove Nova API docker containers
    hosts: all
    roles:
      - tripleo-docker-rm
    vars:
      containers_to_rm:
        - nova_api
        - nova_api_cron
      container_cli: podman

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
