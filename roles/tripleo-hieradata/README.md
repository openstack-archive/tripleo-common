tripleo-hieradata
=================

An Ansible role to hieradata files.

Role variables
--------------

Required:

* `hieradata_template` -- path to template of hieradata content
* `hieradata_variable_start_string` -- string marking the beginning of a template print statement.
* `hieradata_variable_end_string` -- string marking the end of a template print statement.
* `hieradata_per_host` -- whether or not we configure hieradata per host.
* `hieradata_files` -- List of hieradata files (Order matters for Hierarchy).

Test playbook
-------------

Assuming you have tripleo-inventory.yml generated, you can run the
test playbook like:

    ANSIBLE_ROLES_PATH=tripleo-common/roles \
    ANSIBLE_HOST_KEY_CHECKING=False \
    ansible-playbook \
        -i tripleo-inventory.yml \
        tripleo-common/roles/tripleo-hieradata/test-playbook.yml

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
