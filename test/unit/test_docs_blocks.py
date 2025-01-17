import os
import unittest

from dbt.contracts.files import SourceFile, FileHash, FilePath
from dbt.contracts.graph.manifest import Manifest
from dbt.contracts.graph.parsed import ParsedDocumentation
from dbt.node_types import NodeType
from dbt.parser import docs
from dbt.parser.search import FileBlock

from .utils import config_from_parts_or_dicts


SNOWPLOW_SESSIONS_DOCS = r'''
This table contains one record for every session recorded by Snowplow.
A session is itself comprised of pageviews that all occur within 30 minutes
of each other. If more than 30 minutes elapse between pageviews, then a
new session is created. Given the following pageviews:

| session_id | page_view_id | page_title |
| ---------- | ------------ | ---------- |
| abc        | 123          | Home       |
| abc        | 456          | About      |
| abc        | 789          | Home       |

The following sessions will be created:

| session_id | first_page_title | count_pageviews |
| ---------- | ---------------- | --------------- |
| abc        | 123              | 2               |
| abc        | 789              | 1               |
'''

SNOWPLOW_SESSIONS_SESSION_ID_DOCS = r'''
This column is the unique identifier for a Snowplow session. It is generated by
a cookie then expires after 30 minutes of inactivity.
'''

SNOWPLOW_SESSIONS_BLOCK = r'''
{{% docs snowplow_sessions %}}
{snowplow_sessions_docs}
{{% enddocs %}}
'''.format(
        snowplow_sessions_docs=SNOWPLOW_SESSIONS_DOCS
).strip()


SNOWPLOW_SESSIONS_SESSION_ID_BLOCK = r'''
{{% docs snowplow_sessions__session_id %}}
{snowplow_sessions_session_id_docs}
{{% enddocs %}}
'''.format(
    snowplow_sessions_session_id_docs=SNOWPLOW_SESSIONS_SESSION_ID_DOCS
).strip()


TEST_DOCUMENTATION_FILE = r'''
{sessions_block}

{session_id_block}
'''.format(
    sessions_block=SNOWPLOW_SESSIONS_BLOCK,
    session_id_block=SNOWPLOW_SESSIONS_SESSION_ID_BLOCK,
)


MULTIPLE_RAW_BLOCKS = r'''
{% docs some_doc %}
{% raw %}
    ```
    {% docs %}some doc{% enddocs %}
    ```
{% endraw %}
{% enddocs %}

{% docs other_doc %}
{% raw %}
    ```
    {% docs %}other doc{% enddocs %}
    ```
{% endraw %}
{% enddocs %}
'''


class DocumentationParserTest(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            self.root_path = 'C:\\test_root'
            self.subdir_path = 'C:\\test_root\\test_subdir'
            self.testfile_path = 'C:\\test_root\\test_subdir\\test_file.md'
        else:
            self.root_path = '/test_root'
            self.subdir_path = '/test_root/test_subdir'
            self.testfile_path = '/test_root/test_subdir/test_file.md'

        profile_data = {
            'outputs': {
                'test': {
                    'type': 'postgres',
                    'host': 'localhost',
                    'schema': 'analytics',
                    'user': 'test',
                    'pass': 'test',
                    'dbname': 'test',
                    'port': 1,
                }
            },
            'target': 'test',
        }
        root_project = {
            'name': 'root',
            'version': '0.1',
            'profile': 'test',
            'project-root': self.root_path,
            'config-version': 2,
        }

        subdir_project = {
            'name': 'some_package',
            'version': '0.1',
            'profile': 'test',
            'project-root': self.subdir_path,
            'quoting': {},
            'config-version': 2,
        }
        self.root_project_config = config_from_parts_or_dicts(
            project=root_project, profile=profile_data
        )
        self.subdir_project_config = config_from_parts_or_dicts(
            project=subdir_project, profile=profile_data
        )

    def _build_file(self, contents, relative_path) -> FileBlock:
        match = FilePath(
            relative_path=relative_path,
            project_root=self.root_path,
            searched_path=self.subdir_path,
            modification_time=0.0,
        )
        source_file = SourceFile(path=match, checksum=FileHash.empty())
        source_file.contents = contents
        return FileBlock(file=source_file)

    def test_load_file(self):
        parser = docs.DocumentationParser(
            root_project=self.root_project_config,
            manifest=Manifest(),
            project=self.subdir_project_config,
        )

        file_block = self._build_file(TEST_DOCUMENTATION_FILE, 'test_file.md')

        parser.parse_file(file_block)
        docs_values = sorted(parser.manifest.docs.values(), key=lambda n: n.name)
        self.assertEqual(len(docs_values), 2)
        for result in docs_values:
            self.assertIsInstance(result, ParsedDocumentation)
            self.assertEqual(result.package_name, 'some_package')
            self.assertEqual(result.original_file_path, self.testfile_path)
            self.assertEqual(result.resource_type, NodeType.Documentation)
            self.assertEqual(result.path, 'test_file.md')

        self.assertEqual(docs_values[0].name, 'snowplow_sessions')
        self.assertEqual(docs_values[1].name, 'snowplow_sessions__session_id')

    def test_load_file_extras(self):
        TEST_DOCUMENTATION_FILE + '{% model foo %}select 1 as id{% endmodel %}'

        parser = docs.DocumentationParser(
            root_project=self.root_project_config,
            manifest=Manifest(),
            project=self.subdir_project_config,
        )

        file_block = self._build_file(TEST_DOCUMENTATION_FILE, 'test_file.md')

        parser.parse_file(file_block)
        docs_values = sorted(parser.manifest.docs.values(), key=lambda n: n.name)
        self.assertEqual(len(docs_values), 2)
        for result in docs_values:
            self.assertIsInstance(result, ParsedDocumentation)
        self.assertEqual(docs_values[0].name, 'snowplow_sessions')
        self.assertEqual(docs_values[1].name, 'snowplow_sessions__session_id')

    def test_multiple_raw_blocks(self):
        parser = docs.DocumentationParser(
            root_project=self.root_project_config,
            manifest=Manifest(),
            project=self.subdir_project_config,
        )

        file_block = self._build_file(MULTIPLE_RAW_BLOCKS, 'test_file.md')

        parser.parse_file(file_block)
        docs_values = sorted(parser.manifest.docs.values(), key=lambda n: n.name)
        self.assertEqual(len(docs_values), 2)
        for result in docs_values:
            self.assertIsInstance(result, ParsedDocumentation)
            self.assertEqual(result.package_name, 'some_package')
            self.assertEqual(result.original_file_path, self.testfile_path)
            self.assertEqual(result.resource_type, NodeType.Documentation)
            self.assertEqual(result.path, 'test_file.md')

        self.assertEqual(docs_values[0].name, 'other_doc')
        self.assertEqual(docs_values[0].block_contents, '```\n    {% docs %}other doc{% enddocs %}\n    ```')
        self.assertEqual(docs_values[1].name, 'some_doc')
        self.assertEqual(docs_values[1].block_contents, '```\n    {% docs %}some doc{% enddocs %}\n    ```', )
