import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.summarize_scrape_status import annotation_text, main, table_text


class ScrapeSummarySecurityTests(unittest.TestCase):
    def test_workflow_command_escaping(self):
        self.assertEqual(annotation_text("bad%0A\r\n::error::fake"),
                         "bad%250A%0D%0A::error::fake")

    def test_summary_text_cannot_inject_html_links_or_rows(self):
        value = table_text('<img src=x>\n| [click](https://example.invalid) `code`')
        self.assertNotIn('<img', value)
        self.assertNotIn('\n', value)
        self.assertIn(r'\[click\]\(', value)
        self.assertIn(r'\|', value)

    def test_untrusted_status_only_emits_one_warning_and_keeps_table_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            statuses = root / 'reports/scrape-status'
            statuses.mkdir(parents=True)
            (statuses / 'nl-plus.json').write_text(json.dumps({
                'country': 'nl', 'store': 'plus', 'outcome': 'preserved', 'final': 10,
                'reason': 'timeout\r\n::error::forged\n| fake | row | <script> |',
            }))
            (statuses / 'invalid.json').write_text('[]')
            output = io.StringIO()
            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(root / 'summary.md')}), contextlib.redirect_stdout(output):
                    self.assertEqual(main(), 0)
            finally:
                os.chdir(previous)
            lines = output.getvalue().splitlines()
            self.assertEqual(sum(line.startswith('::warning::') for line in lines), 2)
            self.assertFalse(any(line.startswith('::error::') for line in lines))
            summary = (root / 'summary.md').read_text()
            self.assertNotIn('<script>', summary)
            self.assertNotIn('\n| fake', summary)
