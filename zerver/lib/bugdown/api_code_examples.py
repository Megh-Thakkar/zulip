import re
import os
import sys
import ujson
import inspect

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from typing import Any, Dict, Optional, List
import markdown

import zerver.lib.api_test_helpers

REGEXP = re.compile(r'\{generate_code_example\|\s*(.+?)\s*\|\s*(.+?)\s*(\(\s*(.+?)\s*\))?\}')

PYTHON_CLIENT_CONFIG_LINES = """
#!/usr/bin/env python3

import zulip

# Download ~/zuliprc-dev from your dev server
client = zulip.Client(config_file="~/zuliprc-dev")

"""

PYTHON_CLIENT_ADMIN_CONFIG = """
#!/usr/bin/env python

import zulip

# You need a zuliprc-admin with administrator credentials
client = zulip.Client(config_file="~/zuliprc-admin")

"""


class APICodeExamplesGenerator(Extension):
    def extendMarkdown(self, md: markdown.Markdown, md_globals: Dict[str, Any]) -> None:
        md.preprocessors.add(
            'generate_code_example', APICodeExamplesPreprocessor(md, self.getConfigs()), '_begin'
        )


class APICodeExamplesPreprocessor(Preprocessor):
    def __init__(self, md: markdown.Markdown, config: Dict[str, Any]) -> None:
        super(APICodeExamplesPreprocessor, self).__init__(md)

    def run(self, lines: List[str]) -> List[str]:
        done = False
        while not done:
            for line in lines:
                loc = lines.index(line)
                match = REGEXP.search(line)

                if match:
                    function = match.group(1)
                    key = match.group(2)
                    argument = match.group(4)

                    if key == 'fixture':
                        if argument:
                            text = self.render_fixture(function, name=argument)
                        else:
                            text = self.render_fixture(function)
                    elif key == 'example':
                        if argument == 'admin_config=True':
                            text = self.render_code_example(function, admin_config=True)
                        else:
                            text = self.render_code_example(function)

                    # The line that contains the directive to include the macro
                    # may be preceded or followed by text or tags, in that case
                    # we need to make sure that any preceding or following text
                    # stays the same.
                    line_split = REGEXP.split(line, maxsplit=0)
                    preceding = line_split[0]
                    following = line_split[-1]
                    text = [preceding] + text + [following]
                    lines = lines[:loc] + text + lines[loc+1:]
                    break
            else:
                done = True
        return lines

    def render_fixture(self, function: str, name: Optional[str]=None) -> List[str]:
        fixture = []

        if name:
            fixture_dict = zerver.lib.api_test_helpers.FIXTURES[function][name]
        else:
            fixture_dict = zerver.lib.api_test_helpers.FIXTURES[function]

        fixture_json = ujson.dumps(fixture_dict, indent=4, sort_keys=True)

        fixture.append('```')
        fixture.extend(fixture_json.splitlines())
        fixture.append('```')

        return fixture

    def render_code_example(self, function: str, admin_config: Optional[bool]=False) -> List[str]:
        method = zerver.lib.api_test_helpers.TEST_FUNCTIONS[function]
        function_source_lines = inspect.getsourcelines(method)[0]

        if admin_config:
            config = PYTHON_CLIENT_ADMIN_CONFIG.splitlines()
        else:
            config = PYTHON_CLIENT_CONFIG_LINES.splitlines()

        snippet = self.extractCodeExample(function_source_lines, [])

        code_example = []
        code_example.append('```python')
        code_example.extend(config)

        for line in snippet:
            # Remove one level of indentation and strip newlines
            code_example.append(line[4:].rstrip())

        code_example.append('```')

        return code_example

    def extractCodeExample(self, source: List[str], snippet: List[str]) -> List[str]:
        ce_regex = re.compile(r'\# \{code_example\|\s*(.+?)\s*\}')

        start = -1
        end = -1
        for line in source:
            match = ce_regex.search(line)
            if match:
                if match.group(1) == 'start':
                    start = source.index(line)
                elif match.group(1) == 'end':
                    end = source.index(line)
                    break

        if (start == -1 and end == -1):
            return snippet

        snippet.extend(source[start + 1: end])
        snippet.append('    print(result)')
        snippet.append('\n')
        source = source[end + 1:]
        return self.extractCodeExample(source, snippet)


def makeExtension(*args: Any, **kwargs: str) -> APICodeExamplesGenerator:
    return APICodeExamplesGenerator(kwargs)
