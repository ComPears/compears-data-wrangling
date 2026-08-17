from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import sanitize_all_stores


class SanitizePipelineTests(unittest.TestCase):
    def test_contract_upgrade_dedupes_and_quarantines_without_losing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            catalog.write_text(
                json.dumps(
                    [
                        {"n": "Barilla Spaghetti 500 g", "p": "1.80", "s": "500 g", "bn": "Barilla"},
                        {"n": "Barilla Spaghetti 500 g", "p": "1.50", "s": "500 g", "bn": "Barilla"},
                        {"n": "Bad Price Milk 1 l", "p": "0", "s": "1 l"},
                        {"n": "Silvercrest Kaffeemaschine 1.2 l", "p": "39.99", "s": "1.2 l"},
                    ]
                ),
                encoding="utf-8",
            )
            quarantine = root / "reports" / "quarantine"

            with (
                patch.object(sanitize_all_stores, "ROOT", root),
                patch.object(sanitize_all_stores, "QUARANTINE_DIR", quarantine),
                patch.object(sanitize_all_stores, "country_config", return_value={"currency": "EUR"}),
            ):
                stats = sanitize_all_stores.sanitize_file(
                    "de",
                    "example",
                    "catalog.json",
                    observed_at="2026-08-17T12:00:00Z",
                )

            rows = json.loads(catalog.read_text(encoding="utf-8"))
            rejected = json.loads((quarantine / "de-example.json").read_text(encoding="utf-8"))

        self.assertEqual(stats, {"input": 4, "kept": 1, "rejected": 2, "deduped": 1})
        self.assertEqual(rows[0]["p"], "1.50")
        self.assertEqual(rows[0]["schemaVersion"], 2)
        self.assertEqual(rows[0]["country"], "de")
        self.assertEqual(rows[0]["retailer"], "example")
        self.assertEqual(rows[0]["observedAt"], "2026-08-17T12:00:00+00:00")
        self.assertEqual({row["reason"] for row in rejected}, {"invalid_price", "durable_non_grocery"})
        self.assertTrue(all("row" in row for row in rejected))


if __name__ == "__main__":
    unittest.main()
