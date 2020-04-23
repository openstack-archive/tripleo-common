#!/bin/bash

# Create log dir for Keystone logs
KEYSTONE_LOG_DIR="/var/log/keystone"
if [[ ! -d "${KEYSTONE_LOG_DIR}" ]]; then
    mkdir -p ${KEYSTONE_LOG_DIR}
fi
if [[ $(stat -c %U:%G ${KEYSTONE_LOG_DIR}) != "keystone:kolla" ]]; then
    chown keystone:kolla ${KEYSTONE_LOG_DIR}
fi
if [ ! -f "${KEYSTONE_LOG_DIR}/keystone.log" ]; then
    touch ${KEYSTONE_LOG_DIR}/keystone.log
fi
if [[ $(stat -c %U:%G ${KEYSTONE_LOG_DIR}/keystone.log) != "keystone:keystone" ]]; then
    chown keystone:keystone ${KEYSTONE_LOG_DIR}/keystone.log
fi
if [[ $(stat -c %a ${KEYSTONE_LOG_DIR}) != "755" ]]; then
    chmod 755 ${KEYSTONE_LOG_DIR}
fi

EXTRA_KEYSTONE_MANAGE_ARGS=${EXTRA_KEYSTONE_MANAGE_ARGS-}
# Bootstrap and exit if KOLLA_BOOTSTRAP variable is set. This catches all cases
# of the KOLLA_BOOTSTRAP variable being set, including empty.
if [[ "${!KOLLA_BOOTSTRAP[@]}" ]]; then
    sudo -H -u keystone keystone-manage ${EXTRA_KEYSTONE_MANAGE_ARGS} db_sync
    exit 0
fi

. /usr/local/bin/kolla_httpd_setup

ARGS="-DFOREGROUND"
