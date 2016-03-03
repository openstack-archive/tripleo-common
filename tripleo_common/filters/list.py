# Copyright 2016 Red Hat, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import nova

from tripleo_common.filters import capabilities_filter


def tripleo_filters():
    """Return a list of filter classes for TripleO

    This is a wrapper around the Nova all_filters function so we can add our
    filters to the resulting list.
    """
    nova_filters = nova.scheduler.filters.all_filters()
    return (nova_filters + [capabilities_filter.TripleOCapabilitiesFilter])
