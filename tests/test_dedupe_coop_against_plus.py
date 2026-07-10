from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.dedupe_coop_against_plus import dedupe_coop_against_plus


class DedupeCoopAgainstPlusTests(unittest.TestCase):
    def test_removes_coop_rows_already_present_in_plus(self):
        plus_rows = [
            {"n": "Halfvolle melk", "p": "1.29", "ik": "tok:milk|halfvolle|1000", "cn": "halfvolle melk"},
            {"n": "Kaas", "p": "2.50", "ik": "tok:kaas|jong|200", "cn": "kaas jong"},
        ]
        coop_rows = [
            {"n": "Halfvolle melk", "p": "1.35", "ik": "tok:milk|halfvolle|1000", "cn": "halfvolle melk"},
            {"n": "Coop-only brood", "p": "1.10", "ik": "tok:brood|coop-only|400", "cn": "coop only brood"},
            {"n": "Kaas", "p": "2.60", "ik": "tok:kaas|jong|200", "cn": "kaas jong"},
        ]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plus_path = root / "plus.json"
            coop_path = root / "coop.json"
            plus_path.write_text(json.dumps(plus_rows), encoding="utf-8")
            coop_path.write_text(json.dumps(coop_rows), encoding="utf-8")

            with mock.patch(
                "scripts.dedupe_coop_against_plus.catalog_path",
                side_effect=lambda country, slug: plus_path if slug == "plus" else coop_path,
            ):
                stats = dedupe_coop_against_plus(write=True)

            kept = json.loads(coop_path.read_text(encoding="utf-8"))

        self.assertEqual(stats["coop_before"], 3)
        self.assertEqual(stats["removed_overlap"], 2)
        self.assertEqual(stats["coop_after"], 1)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["ik"], "tok:brood|coop-only|400")


if __name__ == "__main__":
    unittest.main()
