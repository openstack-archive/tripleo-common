# TripleO Create Admin #

A role to create an admin user to be later used for running playbooks.

## Role Variables ##

| Name              | Default Value       | Description           |
|-------------------|---------------------|-----------------------|
| `tripleo_admin_user` | `tripleo-admin`     | Name of user to create|
| `tripleo_admin_pubkey` | `[undefined]`     | Public key for authorization|

## Requirements ##

 - ansible >= 2.4
 - python >= 2.6

## Dependencies ##

None

## Example Playbooks ##

### Create and authorize user tripleo-admin ###
    - hosts: localhost
      tasks:
      - import_role:
          name: tripleo-create-admin
        vars:
          tripleo_admin_user: tripleo-admin
          tripleo_admin_pubkey: ssh-rsa AAAA... # etc

### Create user tripleo-admin ###
    - hosts: controller-0
      tasks:
      - import_role:
          name: tripleo-create-admin
          tasks_from: create_user.yml

### Create user tripleo-admin with a keypair ###
    - hosts: undercloud
      tasks:
      - import_role:
          name: tripleo-create-admin
          tasks_from: create_user.yml
        vars: 
          tripleo_admin_generate_key: true

### Authorize existing user ###

    - hosts: localhost
      tasks:
      - import_role:
          name: tripleo-create-admin
          tasks_from: authorize_user.yml
        vars:
          tripleo_admin_user: tripleo-admin
          tripleo_admin_pubkey: ssh-rsa AAAA... # etc
