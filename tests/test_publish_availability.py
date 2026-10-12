import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import publish_healthy_catalogs as publish


class PublishAvailabilityTests(unittest.TestCase):
    def test_rejected_candidate_preserves_recovery_bytes_and_true_last_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            catalog.write_text('[{"observedAt":"2026-10-12T00:00:00Z"}]')
            previous = b'[{"observedAt":"2026-10-07T00:00:00+00:00"}]\n'
            row = {"country": "uk", "store": "tesco", "available": False,
                   "reason_codes": ["invalid_price"], "last_successful_at": "2026-10-12T00:00:00Z"}
            with (patch.object(publish, "ROOT", root),
                  patch.object(publish, "baseline_counts", return_value={}),
                  patch.object(publish, "all_catalog_paths", return_value=[("uk", "tesco", catalog)]),
                  patch.object(publish, "availability_entry", return_value=(row, {}, {})),
                  patch.object(publish.subprocess, "run") as git,
                  patch("scripts.validate_products.validate_file", return_value={})):
                git.return_value.returncode = 0
                git.return_value.stdout = previous
                self.assertEqual(publish.main(), 1)
            self.assertEqual(catalog.read_bytes(), previous)
            self.assertEqual(row["last_successful_at"], "2026-10-07T00:00:00+00:00")
            self.assertEqual(row["catalog_sha256"], hashlib.sha256(previous).hexdigest())

    def test_availability_uses_oldest_observation_expiry_and_catalog_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            old = datetime.now(timezone.utc) - timedelta(hours=12)
            path.write_text(json.dumps([{"observedAt": old.isoformat()},
                                        {"observedAt": datetime.now(timezone.utc).isoformat()}]))
            with (patch.object(publish, "evaluate_catalog", return_value=({}, {"total": 2}, [])),
                  patch.object(publish, "store_config", return_value={})):
                row, _, _ = publish.availability_entry("uk", "aldi-uk", path, {})
            self.assertTrue(row["available"])
            self.assertEqual(row["available_until"], (old + timedelta(hours=48)).isoformat())
            self.assertEqual(row["catalog_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_missing_quantities_make_store_unavailable_not_fake_comparable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text('[{"observedAt":"2026-10-12T00:00:00Z"}]')
            with (patch.object(publish, "evaluate_catalog", return_value=({}, {"total": 1000},
                        ["quantity_coverage_below_minimum"])),
                  patch.object(publish, "store_config", return_value={})):
                row, _, _ = publish.availability_entry("uk", "aldi-uk", path, {})
            self.assertFalse(row["available"])
            self.assertEqual(row["products"], 0)
            self.assertIsNone(row["available_until"])

    def test_partial_outage_publishes_but_complete_outage_fails(self):
        for healthy in (True, False):
            with self.subTest(healthy=healthy), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                catalog = root / "catalog.json"
                catalog.write_text("[]")
                result = {"country": "uk", "store": "tesco", "available": healthy,
                          "reason_codes": [] if healthy else ["stale_scrape_rows"]}
                unavailable = {"country": "uk", "store": "aldi-uk", "available": False,
                               "reason_codes": ["quantity_coverage_below_minimum"]}
                with (patch.object(publish, "ROOT", root),
                      patch.object(publish, "baseline_counts", return_value={}),
                      patch.object(publish, "all_catalog_paths", return_value=[
                          ("uk", "tesco", catalog), ("uk", "aldi-uk", catalog)]),
                      patch.object(publish, "availability_entry", side_effect=[(result, {}, {}), (unavailable, {}, {})]),
                      patch.object(publish.subprocess, "run") as git,
                      patch("scripts.validate_products.validate_file", return_value={})):
                    git.return_value.returncode = 1
                    self.assertEqual(publish.main(), 0 if healthy else 1)
                manifest = json.loads((root / "catalog-availability.json").read_text())
                self.assertEqual(manifest["summary"]["available"], int(healthy))
