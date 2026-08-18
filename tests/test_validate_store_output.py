from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import validate_store_output as output


class ValidateStoreOutputTests(unittest.TestCase):
    def _run(self, *, baseline_profile: int, current_profile: int) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps([{} for _ in range(20)]), encoding="utf-8")
            baseline = root / "data-quality-report.json"
            baseline.write_text(
                json.dumps(
                    [
                        {
                            "country": "nl",
                            "store": "lidl",
                            "total": 100,
                            "quality_profile_version": baseline_profile,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(output, "BASELINE_PATH", baseline),
                patch.object(output, "all_catalog_paths", return_value=[("nl", "lidl", catalog)]),
                patch.object(output, "catalog_rel_path", return_value="catalog.json"),
                patch.object(output, "load_stores_config", return_value={}),
                patch.object(
                    output,
                    "store_config",
                    return_value={
                        "minimum_products": 10,
                        "quality_profile_version": current_profile,
                    },
                ),
                patch.object(sys, "argv", ["validate_store_output.py"]),
            ):
                output.main()

    def test_quality_profile_migration_resets_count_baseline_once(self):
        self._run(baseline_profile=1, current_profile=2)

    def test_drop_still_fails_after_quality_profile_is_established(self):
        with self.assertRaises(SystemExit):
            self._run(baseline_profile=2, current_profile=2)


if __name__ == "__main__":
    unittest.main()
