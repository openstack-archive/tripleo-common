#!/bin/bash

if [[ $(stat -c %U:%G /var/lib/cinder) != "cinder:kolla" ]]; then
    sudo chown -R cinder:kolla /var/lib/cinder
fi
