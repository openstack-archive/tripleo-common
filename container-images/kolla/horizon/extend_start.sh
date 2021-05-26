#!/bin/bash

set -o errexit

FORCE_GENERATE="${FORCE_GENERATE}"
HASH_PATH=/var/lib/kolla/.settings.md5sum.txt
MANAGE_PY="/usr/bin/python3 /usr/bin/manage.py"
PYTHON_VERSION=$(python3 --version | awk '{print $2}' | awk -F'.' '{print $1"."$2}')
SITE_PACKAGES="/usr/lib/python${PYTHON_VERSION}/site-packages"

if [[ -f /etc/openstack-dashboard/custom_local_settings ]]; then
    CUSTOM_SETTINGS_FILE="${SITE_PACKAGES}/openstack_dashboard/local/custom_local_settings.py"
    if [[ ! -L ${CUSTOM_SETTINGS_FILE} ]]; then
        ln -s /etc/openstack-dashboard/custom_local_settings ${CUSTOM_SETTINGS_FILE}
    fi
fi

# Bootstrap and exit if KOLLA_BOOTSTRAP variable is set. This catches all cases
# of the KOLLA_BOOTSTRAP variable being set, including empty.
if [[ "${!KOLLA_BOOTSTRAP[@]}" ]]; then
    $MANAGE_PY migrate --noinput
    exit 0
fi

function config_dashboard {
    ENABLE=$1
    SRC=$2
    DEST=$3
    if [[ ! -f ${SRC} ]]; then
        echo "WARNING: ${SRC} is required"
    elif [[ "${ENABLE}" == "yes" ]] && [[ ! -f "${DEST}" ]]; then
        cp -a "${SRC}" "${DEST}"
        FORCE_GENERATE="yes"
    elif [[ "${ENABLE}" != "yes" ]] && [[ -f "${DEST}" ]]; then
        # remove pyc pyo files too
        rm -f "${DEST}" "${DEST}c" "${DEST}o"
        FORCE_GENERATE="yes"
    fi
}

function config_designate_dashboard {
    for file in ${SITE_PACKAGES}/designatedashboard/enabled/_*[^__].py; do
        config_dashboard "${ENABLE_DESIGNATE}" \
            "${SITE_PACKAGES}/designatedashboard/enabled/${file##*/}" \
            "${SITE_PACKAGES}/openstack_dashboard/local/enabled/${file##*/}"
    done
}

function config_heat_dashboard {
    for file in ${SITE_PACKAGES}/heat_dashboard/enabled/_*[^__].py; do
        config_dashboard "${ENABLE_HEAT}" \
            "${SITE_PACKAGES}/heat_dashboard/enabled/${file##*/}" \
            "${SITE_PACKAGES}/openstack_dashboard/local/enabled/${file##*/}"
    done

    config_dashboard "${ENABLE_HEAT}" \
        "${SITE_PACKAGES}/heat_dashboard/conf/heat_policy.json" \
        "/etc/openstack-dashboard/heat_policy.json"
}

function config_ironic_dashboard {
    for file in ${SITE_PACKAGES}/ironic_ui/enabled/_*[^__].py; do
        config_dashboard "${ENABLE_IRONIC}" \
            "${SITE_PACKAGES}/ironic_ui/enabled/${file##*/}" \
            "${SITE_PACKAGES}/openstack_dashboard/local/enabled/${file##*/}"
    done
}

function config_manila_ui {
    for file in ${SITE_PACKAGES}/manila_ui/local/enabled/_*[^__].py; do
        config_dashboard "${ENABLE_MANILA}" \
            "${SITE_PACKAGES}/manila_ui/local/enabled/${file##*/}" \
            "${SITE_PACKAGES}/openstack_dashboard/local/enabled/${file##*/}"
    done
}

function config_octavia_dashboard {
    config_dashboard "${ENABLE_OCTAVIA}" \
        "${SITE_PACKAGES}/octavia_dashboard/enabled/_1482_project_load_balancer_panel.py" \
        "${SITE_PACKAGES}/openstack_dashboard/local/enabled/_1482_project_load_balancer_panel.py"
}

# Regenerate the compressed javascript and css if any configuration files have
# changed.  Use a static modification date when generating the tarball
# so that we only trigger on content changes.
function settings_bundle {
    tar -cf- --mtime=1970-01-01 \
        /etc/openstack-dashboard/local_settings \
        /etc/openstack-dashboard/custom_local_settings \
        /etc/openstack-dashboard/local_settings.d 2> /dev/null
}

function settings_changed {
    changed=1

    if [[ ! -f $HASH_PATH  ]] || ! settings_bundle | md5sum -c --status $HASH_PATH || [[ $FORCE_GENERATE == yes ]]; then
        changed=0
    fi

    return ${changed}
}

config_designate_dashboard
config_heat_dashboard
config_ironic_dashboard
config_manila_ui
config_octavia_dashboard

if settings_changed; then
    ${MANAGE_PY} collectstatic --noinput --clear
    ${MANAGE_PY} compress --force
    settings_bundle | md5sum > $HASH_PATH
fi

if [[ -f ${SITE_PACKAGES}/openstack_dashboard/local/.secret_key_store ]] && [[ $(stat -c %U ${SITE_PACKAGES}/openstack_dashboard/local/.secret_key_store) != "horizon" ]]; then
    chown horizon ${SITE_PACKAGES}/openstack_dashboard/local/.secret_key_store
fi

. /usr/local/bin/kolla_httpd_setup
