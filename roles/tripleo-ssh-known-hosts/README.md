tripleo-ssh-known-hosts
=======================

An Ansible role to add all SSH host keys to the host level known hosts file on
all hosts.

Requirements
------------

This section needs to be documented.

Role variables
--------------

- ssh_known_hosts: -- Dict of hostname to ssh_known_hosts entries for a given
  host

Dependencies
------------

None.

Example Playbook
----------------

Sample playbook to call the role:

  - name: Configure SSH known hosts
    hosts: all
    roles:
      - tripleo-ssh-known-hosts

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
