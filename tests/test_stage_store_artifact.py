from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import stage_store_artifact


class StageStoreArtifactTests(unittest.TestCase):
    def test_raw_observations_are_staged_with_content_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            raw = store / "raw"
            raw.mkdir(parents=True)
            source = raw / "search.json"
            source.write_text('[{"name":"Milk"}]', encoding="utf-8")
            output = root / "artifacts" / "raw"

            with (
                patch.object(
                    stage_store_artifact,
                    "store_config",
                    return_value={"intermediate_globs": ["raw/*.json"]},
                ),
                patch.object(stage_store_artifact, "store_dir", return_value=store),
            ):
                count = stage_store_artifact._stage_raw(
                    "uk",
                    "tesco",
                    output,
                    scrape_status={"outcome": "preserved", "reason": "generated zero rows"},
                )

            staged = output / "uk" / "tesco" / "raw" / "search.json"
            manifest_path = output / "uk" / "tesco" / "manifest.json"
            staged_text = staged.read_text(encoding="utf-8")
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(count, 1)
        self.assertEqual(staged_text, '[{"name":"Milk"}]')
        self.assertEqual(payload["files"][0]["path"], "raw/search.json")
        self.assertEqual(payload["scrapeStatus"]["outcome"], "preserved")
        self.assertEqual(payload["files"][0]["sha256"], hashlib.sha256(b'[{"name":"Milk"}]').hexdigest())


if __name__ == "__main__":
    unittest.main()
