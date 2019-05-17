# Copyright 2015 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


def create_disk_images():
    disk_images = {
        'disk_images': [{
            'arch': 'amd64',
            'distro': 'some_awesome_os',
            'imagename': 'overcloud',
            'type': 'qcow2',
            'elements': ['image_element']
        }]
    }

    return disk_images


def create_parsed_upload_images():
    uploads = [
        {'imagename': 'docker.io/tripleostein/'
                      'heat-docker-agents-centos:latest',
         'push_destination': 'localhost:8787'},
        {'imagename': 'docker.io/tripleostein/'
                      'centos-binary-nova-compute:liberty',
         'push_destination': 'localhost:8787'},
        {'imagename': 'docker.io/tripleostein/'
                      'centos-binary-nova-libvirt:liberty',
         'push_destination': '192.0.2.0:8787'},
        {'imagename': 'docker.io/tripleostein/'
                      'image-with-missing-tag',
         'push_destination': 'localhost:8787'},
    ]
    return uploads
