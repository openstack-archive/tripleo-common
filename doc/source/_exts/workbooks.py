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

from docutils import nodes
from docutils.parsers import rst
from docutils.statemachine import ViewList
from sphinx.util.nodes import nested_parse_with_titles
import yaml


WORKFLOW_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../../workbooks', ))


def _title(name):
    return name.replace('_', ' ').capitalize() + " Workbook"


def _workbook_to_rst(name, workbook):

    title = _title(name)

    yield '.. _workbook-%s:' % name
    yield ''
    yield '=' * len(title)
    yield title
    yield '=' * len(title)
    yield ''
    yield ':Workbook name: {}'.format(workbook['name'])
    yield ''
    if 'description' in workbook:
        yield workbook['description']
        yield ''
    yield 'Workflows in the {} Workbook'.format(title)
    yield ''

    for wf_name, workflow in sorted(workbook['workflows'].items()):

        yield '.. object:: ' + workbook['name'] + '.' + wf_name
        yield ''

        if 'type' in workflow:
            yield '   :type: {}'.format(workflow['type'])
            yield ''

        if 'description' in workflow:
            yield '   {}'.format(workflow['description'])
            yield ''

        if 'input' in workflow:
            yield '   Workflow inputs:'
            yield ''
            for input_param in workflow['input']:
                try:
                    yield '   :input {}: Default: {}'.format(
                        *input_param.items()[0])
                except:
                    yield '   :input {}: Required.'.format(input_param)
            yield ''


def get_workbooks():

    all_workbooks = {}

    for root, dirs, files in os.walk(WORKFLOW_PATH):
        for file in files:
            with open(os.path.join(root, file)) as f:
                all_workbooks[file.split('.')[0]] = yaml.safe_load(f)

    return all_workbooks


def _write_workbook_pages(app):
    all_workbooks = get_workbooks()
    files = []

    for name, workbook in all_workbooks.items():
        filename = 'doc/source/reference/workbooks/%s.rst' % name
        app.info('generating workbook page for %s' % name)
        with open(filename, 'w') as f:
            f.write('\n'.join(_workbook_to_rst(name, workbook)))
        files.append(filename)
    return files


class WorkflowListDirective(rst.Directive):

    has_content = False

    def run(self):
        all_workbooks = get_workbooks()

        # Build the view of the data to be parsed for rendering.
        result = ViewList()
        for workbook_name in sorted(all_workbooks.keys()):
            workbook = all_workbooks[workbook_name]
            for line in _workbook_to_rst(workbook_name, workbook):
                result.append(line, '<' + __name__ + '>')

        # Parse what we have into a new section.
        node = nodes.section()
        node.document = self.state.document
        nested_parse_with_titles(self.state, result, node)

        return node.children


def setup(app):
    app.info('loading workbooks extension')
    app.add_directive('workbooklist', WorkflowListDirective)
    _write_workbook_pages(app)
