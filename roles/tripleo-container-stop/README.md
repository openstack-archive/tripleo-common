tripleo-container-stop
======================

An Ansible role to stop containers.

Role variables
--------------

- tripleo_containers_to_stop: -- Containers names to stop.
- tripleo_delegate_to: -- Delegate the execution of this role.

Example Playbook
----------------

Sample playbook to call the role:

  - name: Stop a set of container
    hosts: all
    roles:
      - tripleo-container-stop
    vars:
      tripleo_containers_to_stop:
        - nova_api
        - nova_api_cron
      tripleo_delegate_to: localhost

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
