tripleo-transfer
================

An Ansible role to files from one overcloud node to another one.

Role variables
--------------

Required:

* `tripleo_transfer_src_host` -- the inventory name of the source host
* `tripleo_transfer_src_dir` -- directory on the source host to
  transfer from
* `tripleo_transfer_dest_host` -- the inventory name of the
  destination host
* `tripleo_transfer_dest_dir` -- directory on the destination host to
  transfer to

Optional:

* `tripleo_transfer_storage_root_dir` -- directory on the Ansible host
  under which all data is temporarily stored
  (defaults to "/var/lib/mistral/tripleo-transfer")
* `tripleo_transfer_storage_root_become` -- whether to use `become`
  when creating the storage root directory
  (defaults to false)
* `tripleo_transfer_src_become` -- whether to use `become`
  on the source host
  (defaults to true)
* `tripleo_transfer_dest_become` -- whether to use `become`
  on the destination host
  (defaults to true)
* `tripleo_transfer_dest_wipe` -- whether to wipe the destination
  directory before transferring the content
  (defaults to true)

Test playbook
-------------

Assuming you have tripleo-inventory.yml generated, you can run the
test playbook like:

    ANSIBLE_ROLES_PATH=tripleo-common/roles \
    ANSIBLE_HOST_KEY_CHECKING=False \
    ansible-playbook \
        -i tripleo-inventory.yml \
        tripleo-common/roles/tripleo-transfer/test-playbook.yml

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
