from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import write_catalog_manifest as manifest


class CatalogManifestTests(unittest.TestCase):
    def test_failed_attempt_cannot_refresh_old_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            catalog.write_text(
                json.dumps([{"n": "Milk", "observedAt": "2020-01-01T00:00:00Z"}]),
                encoding="utf-8",
            )
            statuses = root / "status"
            statuses.mkdir()
            attempted = datetime.now(timezone.utc).isoformat()
            (statuses / "uk-tesco.json").write_text(
                json.dumps(
                    {
                        "country": "uk",
                        "store": "tesco",
                        "outcome": "preserved",
                        "attempted_at": attempted,
                    }
                ),
                encoding="utf-8",
            )
            output = root / "manifest.json"
            with (
                patch.object(manifest, "all_catalog_paths", return_value=[("uk", "tesco", catalog)]),
                patch.object(manifest, "catalog_rel_path", return_value="catalog.json"),
                patch.object(manifest, "store_config", return_value={"minimum_products": 1}),
                patch.object(
                    sys,
                    "argv",
                    [
                        "write_catalog_manifest.py",
                        "--output",
                        str(output),
                        "--status-dir",
                        str(statuses),
                    ],
                ),
            ):
                code = manifest.main()
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(code, 1)
        self.assertEqual(payload["summary"]["required_ok"], 0)
        self.assertEqual(payload["stores"][0]["attempted_at"], attempted)
        self.assertEqual(payload["stores"][0]["last_successful_at"], "2020-01-01T00:00:00+00:00")

    def test_all_required_catalogs_must_be_fresh_before_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            observed = datetime.now(timezone.utc).isoformat()
            catalog.write_text(json.dumps([{"n": "Milk", "observedAt": observed}]), encoding="utf-8")
            output = root / "manifest.json"
            with (
                patch.object(manifest, "all_catalog_paths", return_value=[("uk", "tesco", catalog)]),
                patch.object(manifest, "catalog_rel_path", return_value="catalog.json"),
                patch.object(manifest, "store_config", return_value={"minimum_products": 1}),
                patch.object(
                    sys,
                    "argv",
                    ["write_catalog_manifest.py", "--output", str(output), "--status-dir", str(root / "missing")],
                ),
            ):
                code = manifest.main()
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["summary"]["required_ok"], 1)


if __name__ == "__main__":
    unittest.main()
