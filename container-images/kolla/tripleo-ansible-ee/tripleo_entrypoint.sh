#!/usr/bin/env bash

# Adding tripleo ansible-runner specific scripts here
# Expand the variables
eval "echo \"$(cat /runner/env/settings)\"" > /runner/env/settings

# Contents from ansible-runner entrypoint
