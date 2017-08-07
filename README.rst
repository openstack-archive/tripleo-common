==============
tripleo-common
==============

A common library for TripleO workflows.

* Free software: Apache license
* Documentation: http://docs.openstack.org/developer/tripleo-common
* Source: http://git.openstack.org/cgit/openstack/tripleo-common
* Bugs: http://bugs.launchpad.net/tripleo-common

Action Development
------------------


When developing new actions, you will checkout a copy of tripleo-common to an
undercloud machine and add actions as needed.  To test the actions they need
to be installed and selected services need to be restarted.  Use the following
code to accomplish these tasks. ::


    sudo rm -Rf /usr/lib/python2.7/site-packages/tripleo_common*
    sudo python setup.py install
    sudo cp /usr/share/tripleo-common/sudoers /etc/sudoers.d/tripleo-common
    sudo systemctl restart openstack-mistral-executor
    sudo systemctl restart openstack-mistral-engine
    # this loads the actions via entrypoints
    sudo mistral-db-manage populate
    # make sure the new actions got loaded
    mistral action-list | grep tripleo

Validations
-----------

Prerequisites
~~~~~~~~~~~~~

If you haven't installed the undercloud with the ``enable_validations`` set to
true, you will have to prepare your undercloud to run the validations::

    $ sudo pip install git+https://git.openstack.org/openstack/tripleo-validations
    $ sudo yum install ansible
    $ sudo useradd validations

Finally you need to generate an SSH keypair for the validation user and copy
it to the overcloud's authorized_keys files::

    $ mistral execution-create tripleo.validations.v1.copy_ssh_key

Running validations using the mistral workflow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a context.json file containing the arguments passed to the workflow::

    {
      "validation_names": ["512e", "rabbitmq-limits"]
    }

Run the ``tripleo.validations.v1.run_validations`` workflow with mistral
client::

    mistral execution-create tripleo.validations.v1.run_validations context.json


Running groups of validations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a context.json file containing the arguments passed to the workflow::

    {
      "group_names": ["network", "post-deployment"]
    }

Run the ``tripleo.validations.v1.run_groups`` workflow with mistral client::

    mistral execution-create tripleo.validations.v1.run_groups context.json
