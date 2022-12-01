#!/usr/bin/env bash

# Adding tripleo ansible-runner specific scripts here
# Expand the variables
eval "echo \"$(cat /runner/env/settings)\"" > /runner/env/settings

if [ -n "$RUNNER_INVENTORY" ]; then
    echo "---" > /runner/inventory/inventory.yaml
    echo "$RUNNER_INVENTORY" >> /runner/inventory/inventory.yaml
fi

if [ -n "$RUNNER_PLAYBOOK" ]; then
    echo "---" > /runner/project/playbook.yaml
    echo "$RUNNER_PLAYBOOK" >> /runner/project/playbook.yaml
fi

# Contents from ansible-runner entrypoint
