tripleo-container-rm
====================

An Ansible role to tear-down containers.

Role variables
--------------

- container_cli: -- Name of the Container CLI tool (default to podman).
- containers_to_rm: -- List of containers to remove.

Example Playbook
----------------

Sample playbook to call the role:

  - name: Remove Nova API docker containers
    hosts: all
    roles:
      - tripleo-container-rm
    vars:
      containers_to_rm:
        - nova_api
        - nova_api_cron

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
