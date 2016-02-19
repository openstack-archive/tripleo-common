===============================
tripleo-common
===============================

A common library for TripleO workflows.

* Free software: Apache license
* Documentation: http://docs.openstack.org/developer/tripleo-common
* Source: http://git.openstack.org/cgit/openstack/tripleo-common
* Bugs: http://bugs.launchpad.net/tripleo-common

Action Development
-------------------


When developing new actions, you will checkout a copy of tripleo-common to an
undercloud machine and add actions as needed.  To test the actions they need
to be installed and selected services need to be restarted.  Use the following
code below to accomplish these tasks.

        sudo rm -Rf /usr/lib/python2.7/site-packages/tripleo_common*
        sudo python setup.py install
        sudo systemctl restart openstack-mistral-executor
        sudo systemctl restart openstack-mistral-engine
        # this loads the actions via entrypoints
        sudo mistral-db-manage populate
        # make sure the new actions got loaded
        mistral action-list | grep tripleo

