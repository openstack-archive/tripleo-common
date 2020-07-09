#!/usr/bin/env python
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

import os
import re
import sys

import yaml


TCIB_MAP = {
    "tcib_path": None,
    "tcib_args": {},
    "tcib_from": None,
    "tcib_labels": {},
    "tcib_envs": {},
    "tcib_onbuilds": [],
    "tcib_volumes": [],
    "tcib_workdir": None,
    "tcib_adds": [],
    "tcib_copies": [],
    "tcib_exposes": [],
    "tcib_user": None,
    "tcib_shell": None,
    "tcib_runs": [],
    "tcib_healthcheck": None,
    "tcib_stopsignal": None,
    "tcib_entrypoint": None,
    "tcib_cmd": None,
    "tcib_actions": [],
    "tcib_gather_files": [],
}

DOCKER_VERB_MAP = {
    "FROM": "tcib_from",
    "RUN": "tcib_runs",
    "CMD": "tcib_cmd",
    "LABEL": "tcib_labels",
    "EXPOSE": "tcib_exposes",
    "ENV": "tcib_envs",
    "ADD": "tcib_adds",
    "COPY": "tcib_copies",
    "ENTRYPOINT": "tcib_entrypoint",
    "VOLUME": "tcib_volumes",
    "USER": "tcib_user",
    "WORKDIR": "tcib_workdir",
    "ARG": "tcib_args",
    "ONBUILD": "tcib_onbuilds",
    "STOPSIGNAL": "tcib_stopsignal",
    "HEALTHCHECK": "tcib_healthcheck",
    "SHELL": "tcib_shell",
}


def line_reader(lines, return_lines=None):
    """Read all lines of a container file.

    This will concatinate all them into a machine readable array.

    :param Lines: list of lines to read.
    :type Lines: List
    :param return_lines: List of lines that will be returned.
    :type return_lines: List
    :returns: List
    """
    if not return_lines:
        return_lines = list()
    try:
        line = next(lines)
        line = line.strip()
        if line:
            if line.endswith("\\"):
                while True:
                    new_line = next(lines)
                    if not new_line.startswith("#"):
                        new_line = new_line.strip()
                        line = line.rstrip("\\")
                        line += " {line}".format(line=new_line.rstrip("\\"))
                        if not new_line.endswith("\\"):
                            break
                return_lines.append(line)
            else:
                if not line.startswith("#"):
                    return_lines.append(line)
    except StopIteration:
        return return_lines
    else:
        return line_reader(lines, return_lines=return_lines)


def package_parse(packages_line, lines):
    """Parse a command line which runs a dnf install.

    :param package_line: Line to parse
    :type package_line: String
    :param lines: List of lines
    :type lines: List
    :returns: List
    """
    a = re.search(r".*dnf -y install (.*?) (&&|' ')", packages_line)
    TCIB_MAP["tcib_packages"] = {"common": sorted(a.group(1).split())}
    index = lines.index(packages_line)
    lines.pop(index)
    lines.insert(
        0,
        packages_line.replace(
            a.group(1), r"{{ tcib_packages.common | join(' ') }}"
        ),
    )
    return lines


def module_parse(module_line, lines):
    """Parse a command line which runs a dnf module.

    :param module_line: Line to parse
    :type module_line: String
    :param lines: List of lines
    :type lines: List
    :returns: List
    """
    modules_list = TCIB_MAP["tcib_packages"]["modules"] = list()
    pattern = re.compile(
        r"dnf -y module (disable|enable|info|install|list|provides|"
        r"remove|repoquery|reset|update)(.*?)(&&|' ')"
    )
    for match in re.findall(pattern, module_line):
        key, value, _ = match
        modules = [i for i in value.split() if i]
        for module in modules:
            modules_list.append({key: module})
    module_jinja = (
        r"RUN if [ '{{ tcib_distro }}' == 'rhel' ]; then "
        r"{% for item in tcib_packages.modules %}"
        r"{% set key, value = (item.items() | list).0 %}"
        r"dnf module -y {{ key }} {{ value }}; "
        r"{% endfor %}fi"
    )
    index = lines.index(module_line)
    lines.pop(index)
    lines.insert(
        index,
        module_line.replace(
            " ".join(
                [
                    i[0]
                    for i in re.findall(
                        r"(dnf -y module.*?(&&|' '))", module_line
                    )
                ]
            ),
            "",
        ),
    )
    lines.insert(index, module_jinja)
    return lines


def line_parser(lines):
    """Line parser which will translate strings into machine data.

    :param lines: List of lines
    :type lines: List
    """
    for line in lines:
        verb, content = line.split(" ", 1)
        if verb in ["ADD", "COPY", "RUN"]:
            TCIB_MAP["tcib_actions"].append({verb.lower(): content.strip()})
        elif verb in ["FROM", "LABEL"]:
            continue
        else:
            map_item = TCIB_MAP[DOCKER_VERB_MAP[verb]]
            if isinstance(map_item, list):
                map_item.append(content)
            elif isinstance(map_item, dict):
                try:
                    key, value = content.split("=", 1)
                except ValueError:
                    key, value = content.split(" ", 1)
                map_item[key] = value.strip('"')
            else:
                TCIB_MAP[DOCKER_VERB_MAP[verb]] = content


def main(containerfile):
    """Run the main application.

    :param containerfile: File to parse, this requires the full path.
    :type containerfile: String
    """
    with open(containerfile) as f:
        lines = [
            " ".join(
                i.split()
            ) for i in line_reader(lines=iter(f.readlines()))
        ]

    r = re.compile(".*dnf.*install(.*)($| )")
    packages_lines = list(filter(r.match, lines))
    if len(packages_lines) == 1:
        lines = package_parse(packages_line=packages_lines[0], lines=lines)
    elif len(packages_lines) > 1:
        print(
            "Warning: packages not parsed because there is more than one "
            "install command, file '{}' will need to be manually converted "
            "to using the packages structure.".format(containerfile)
        )

    r = re.compile(".*dnf.*module(.*)($| )")
    module_lines = list(filter(r.match, lines))
    if len(module_lines) == 1:
        lines = module_parse(module_line=module_lines[0], lines=lines)
    elif len(module_lines) > 1:
        print(
            "Warning: modules not parsed because there is more than one "
            "module command, file '{}' will need to be manually converted to "
            "using the module structure.".format(containerfile)
        )

    line_parser(lines=lines)
    render_vars = dict()
    for key, value in TCIB_MAP.items():
        if value:
            render_vars[key] = value

    dir_path = os.path.dirname(containerfile)
    var_file = "{var}.yaml".format(
        var=os.path.basename(dir_path).replace("-container", "")
    )
    with open(os.path.join(dir_path, var_file), "w") as f:
        f.write(yaml.dump(render_vars, default_flow_style=False, width=4096))


if __name__ == "__main__":
    main(containerfile=sys.argv[1])
