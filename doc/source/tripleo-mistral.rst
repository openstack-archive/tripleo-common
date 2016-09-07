===================
TripleO and Mistral
===================

TripleO is in the process of developing Mistral workflows and actions to expose
TripleO business logic.  This allows RESTful API access to TripleO functions.

- `Spec <https://specs.openstack.org/openstack/tripleo-specs/specs/mitaka/tripleo-mistral-deployment-library.html>`_

A high-level view of the overall workflow can be found in the `TripleO Overcloud
Deployment Library Spec
<https://specs.openstack.org/openstack/tripleo-specs/specs/mitaka/tripleo-overcloud-deployment-library.html>`_.

================
Undercloud Setup
================

To install the undercloud follow the `TripleO developer documentation
<http://docs.openstack.org/developer/tripleo-docs/environments/environments.html>`_.

=============
Code Location
=============

The relevant code is organized as below.  Note that Mistral actions are exposed
through *setup.cfg*.

| tripleo-common/
|  \|
|  + setup.cfg
|  \|
|  + tripleo_common/
|     \|
|     + actions/
|  \|
|  + workbooks/

=============
Using Actions
=============

Mistral actions can be run through the CLI:

::

   echo '{"container": "<container-name>"}' > input.json
   openstack action execution run tripleo.plan.create_container input.json

For REST API usage please reference the `full Mistral documentation
<http://docs.openstack.org/developer/mistral/>`_.

===============
Using Workflows
===============

The undercloud install will automatically load the TripleO Mistral workbooks.
To manually load these workbooks during development, run the following:

::

   openstack workbook create workbooks/plan_management.yaml

Workflow execution is asynchronous.  The output of an execution is an ID that
can be used to get the status and output of that workflow execution.

::

   echo '{"container": "<container-name>"}' > input.json
   openstack workflow execution create tripleo.plan_management.v1.create_default_deployment_plan input.json
   openstack workflow execution show <execution ID>
   openstack workflow execution show output <execution ID>

For REST API usage please reference the `full Mistral documentation
<http://docs.openstack.org/developer/mistral/>`_.

By default a workflow execution expires after 48 hours.  This can be configured
in /etc/mistral/mistral.conf.

::

   [execution_expiration_policy]
   evaluation_interval=120
   older_than=2880

After modifying these values you will need to restart the mistral-engine service.
