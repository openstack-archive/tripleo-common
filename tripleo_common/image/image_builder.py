#   Copyright 2015 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#


import abc
import logging
import os
import shlex
import six
import subprocess
import sys

from tripleo_common.image.exception import ImageBuilderException

if sys.version_info[0] < 3:
    import codecs
    _open = open
    open = codecs.open


@six.add_metaclass(abc.ABCMeta)
class ImageBuilder(object):
    """Base representation of an image building method"""

    @staticmethod
    def get_builder(builder):
        if builder == 'dib':
            return DibImageBuilder()
        raise ImageBuilderException('Unknown image builder type')

    @abc.abstractmethod
    def build_image(self, image_path, image_type, node_dist, arch, elements,
                    options, packages, extra_options={}):
        """Build a disk image"""
        pass


class DibImageBuilder(ImageBuilder):
    """Build images using diskimage-builder"""

    logger = logging.getLogger(__name__ + '.DibImageBuilder')
    handler = logging.StreamHandler(sys.stdout)

    # NOTE(bnemec): This may not play nicely with callers other than the
    # openstackclient.  However, since at this time there are no such other
    # callers we can deal with that if/when it happens.
    def _configure_logging(self):
        """Ensure our info level log output gets seen

        The default openstackclient logging level is warning, which means
        our info messages for the image build are not visible to the user.
        By adding our own local handler we can ensure that the messages get
        logged in a visible way.

        To avoid duplicate log messages, we need to not propagate them to
        parent loggers.  Otherwise we end up with both our handler and the
        parent handler logging warning and above messages.
        """
        if not self.logger.handlers:
            self.logger.addHandler(self.handler)
            self.logger.propagate = False

    def build_image(self, image_path, image_type, node_dist, arch, elements,
                    options, packages, extra_options={}):
        self._configure_logging()
        env = os.environ.copy()

        elements_path = env.get('ELEMENTS_PATH')
        if elements_path is None:
            env['ELEMENTS_PATH'] = os.pathsep.join([
                "/usr/share/tripleo-puppet-elements",
                "/usr/share/instack-undercloud",
                '/usr/share/tripleo-image-elements',
            ])
            os.environ.update(env)

        cmd = ['disk-image-create', '-a', arch, '-o', image_path,
               '-t', image_type]

        if packages:
            cmd.append('-p')
            cmd.append(','.join(packages))

        if options:
            for option in options:
                cmd.extend(shlex.split(option))

        skip_base = extra_options.get('skip_base', False)
        if skip_base:
            cmd.append('-n')

        docker_target = extra_options.get('docker_target')
        if docker_target:
            cmd.append('--docker-target')
            cmd.append(docker_target)

        environment = extra_options.get('environment')
        if environment:
            os.environ.update(environment)

        if node_dist:
            cmd.append(node_dist)

        cmd.extend(elements)

        log_file = '%s.log' % image_path

        self.logger.info('Running %s' % cmd)
        self.logger.info('Logging output to %s' % log_file)
        process = subprocess.Popen(cmd,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        with open(log_file, 'w', encoding='utf-8') as f:
            while True:
                line = process.stdout.readline()
                try:
                    line = line.decode('utf-8')
                except AttributeError:
                    # In Python 3 there is no decode method, but we don't need
                    # to decode because strings are always unicode.
                    pass
                if line:
                    self.logger.info(line.rstrip())
                    f.write(line)
                if line == '' and process.poll() is not None:
                    break
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)
