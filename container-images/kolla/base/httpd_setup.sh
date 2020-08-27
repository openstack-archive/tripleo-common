#!/bin/bash

# This script performs setup necessary to run the Apache httpd web server.
# It should be sourced rather than executed as environment variables are set.

# Assume the service runs on top of Apache httpd when user is root.
if [[ "$(whoami)" == 'root' ]]; then
    # NOTE(pbourke): httpd will not clean up after itself in some cases which
    # results in the container not being able to restart. (bug #1489676, 1557036)
    rm -rf /var/run/httpd/* /run/httpd/* /tmp/httpd*

    # CentOS 8 has an issue with mod_ssl which produces an invalid Apache
    # configuration in /etc/httpd/conf.d/ssl.conf. This causes the following error
    # on startup:
    #   SSLCertificateFile: file '/etc/pki/tls/certs/localhost.crt' does not exist or is empty
    # Work around this by generating certificates manually.
    if [[ ! -e /etc/pki/tls/certs/localhost.crt ]]; then
        /usr/libexec/httpd-ssl-gencerts
    fi
fi
