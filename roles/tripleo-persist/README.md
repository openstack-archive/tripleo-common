tripleo-persist
===============

An Ansible role to temporary persist a files on undercloud and later
restore them.

Role variables
--------------

Required:

* `tripleo_persist_dir` -- directory on the target host to persist

Optional:

* `tripleo_persist_storage_root_dir` -- directory on the Ansible host
  under which all data is stored
  (defaults to "/var/lib/mistral/tripleo-persist")
* `tripleo_persist_storage_root_become` -- whether to use `become`
  when creating the storage root directory
  (defaults to false)

Test playbook
-------------

Assuming you have tripleo-inventory.yml generated, you can run the
test playbook like:

    ANSIBLE_ROLES_PATH=tripleo-common/roles \
    ANSIBLE_HOST_KEY_CHECKING=False \
    ansible-playbook
        -i tripleo-inventory.yml \
        tripleo-common/roles/tripleo-persist/test-playbook.yml \
        -e persist=true

    ANSIBLE_ROLES_PATH=tripleo-common/roles \
    ANSIBLE_HOST_KEY_CHECKING=False \
    ansible-playbook
        -i tripleo-inventory.yml \
        tripleo-common/roles/tripleo-persist/test-playbook.yml \
        -e restore=true

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
