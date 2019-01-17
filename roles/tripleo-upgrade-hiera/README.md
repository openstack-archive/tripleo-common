tripleo-upgrade-hiera
=====================

An Ansible role to set hiera value during upgrade as json value/key.

Role variables
--------------

Required:

* `tripleo_upgrade_key` -- the hiera key to setup. (optional for remove_all)
* `tripleo_upgrade_value` -- the hiera value to setup. (non-needed for remove and remove_all)

Optional:

* `tripleo_upgrade_hiera_file` -- hiera file to were the variable go.
  (defaults to "/etc/puppet/hieradata/upgrade.json")

Test playbook
-------------

Assuming you have tripleo-inventory.yml generated, you can run the
test playbook like:

    ANSIBLE_ROLES_PATH=tripleo-common/roles \
    ANSIBLE_HOST_KEY_CHECKING=False \
    ansible-playbook
        -i tripleo-inventory.yml \
        tripleo-common/roles/tripleo-upgrade-hiera/test-playbook.yml

License
-------

Free software: Apache License (2.0)

Author Information
------------------

OpenStack TripleO team
