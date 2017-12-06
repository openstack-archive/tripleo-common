tripleo-bootstrap
=================

An Ansible role to bootstrap a TripleO deployment.

Requirements
------------

This section needs to be documented.

Role variables
--------------

- packages_bootstrap: -- list of required packages to bootstrap TripleO.

Dependencies
------------

This role needs repositories to be deployed as it works now.

Example Playbook
----------------

Sample playbook to call the role:

  - name: Bootstrap TripleO
    hosts: all
    roles:
      - tripleo-bootstrap

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
