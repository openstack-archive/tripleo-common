tripleo-container-tag
=====================

An Ansible role to deploy an apache based container image serving service.

Role variables
--------------

- container_registry_host: -- Registry host
- container_registry_port: -- Registry port
- image_data_dir: -- Directory to store container image data

Example Playbook
----------------

Sample playbook to call the role:

  - name: Deploy image service
    hosts: undercloud
    roles:
      - tripleo-image-serve
    vars:
      container_registry_host: 192.168.24.1
      container_registry_port: 8787

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
