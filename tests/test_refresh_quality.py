import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import catalog_health, finalize_store_catalog, run_store_pipeline as pipeline
from scripts import sanitize_all_stores, validate_products
from scripts.catalog_count_policy import count_change_errors


class RefreshQualityTests(unittest.TestCase):
    def test_old_morrisons_price_extraction_requires_fresh_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "catalog.json"
            catalog.write_text('[{"sourceMethod":"dom_cards"}]')
            quality = dict(total=1, with_observed_at=1, missing_price=0, contract_errors=0, promo_in_name=0)
            with (patch.object(finalize_store_catalog, "analyze_catalog", return_value={"issues": []}),
                  patch.object(finalize_store_catalog, "validate_file", return_value=quality),
                  patch.object(finalize_store_catalog, "quantity_coverage_messages", return_value=(None, None))):
                errors = finalize_store_catalog.evaluate_catalog("uk", "morrisons", catalog)[2]
            self.assertIn("unverified_morrisons_selling_price", errors)

    def finalize(self, root, rows, *, cfg=None, previous=None):
        catalog = root / "candidate.json"
        catalog.write_text(json.dumps(rows))
        config = {"minimum_products": 1, "minimum_quantity_coverage": 0.85, **(cfg or {})}
        with (patch.object(catalog_health, "store_config", return_value=config),
              patch.object(validate_products, "store_config", return_value=config),
              patch.object(sanitize_all_stores, "QUARANTINE_DIR", root / "quarantine")):
            return finalize_store_catalog.finalize(
                "uk", "aldi-uk", catalog, previous,
                datetime.now(timezone.utc).isoformat(), root / "quality.json")

    def test_usable_catalog_is_sanitized_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.finalize(root, [{"n": "Whole Milk", "p": "1.50", "s": "1 l"}])
            self.assertFalse(result["errors"])
            self.assertEqual(result["quality"]["with_quantity"], 1)
            self.assertEqual(json.loads((root / "candidate.json").read_text())[0]["schemaVersion"], 2)

    def test_missing_prices_are_rejected_before_count_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{"n": f"Whole Milk {i}", "p": "", "s": "1 l"} for i in range(100)]
            with self.assertRaisesRegex(ValueError, "product_count_below_minimum"):
                self.finalize(root, rows)
            report = json.loads((root / "quality.json").read_text())
            self.assertEqual(report["sanitization"]["rejected"], 100)
            self.assertTrue((root / "quarantine/uk-aldi-uk.json").exists())

    def test_optional_refresh_cannot_claim_success_with_missing_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "quantity_coverage_below_minimum"):
                self.finalize(Path(tmp), [{"n": "Strawberry Milk", "p": "0.95"}], cfg={"optional": True})

    def test_existing_stale_observation_is_not_restamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "stale_scrape_rows"):
                self.finalize(Path(tmp), [{"n": "Whole Milk", "p": "1.50", "s": "1 l",
                                          "observedAt": "2020-01-01T00:00:00Z"}])

    def test_count_drop_and_growth_use_shared_publication_policy(self):
        self.assertFalse(count_change_errors(100, 80))
        self.assertFalse(count_change_errors(100, 175))
        self.assertTrue(count_change_errors(100, 79))
        self.assertTrue(count_change_errors(100, 176))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = root / "previous.json"
            previous.write_text(json.dumps([{"schemaVersion": 2}] * 10))
            with self.assertRaisesRegex(ValueError, "count dropped"):
                self.finalize(root, [{"n": "Whole Milk", "p": "1.50", "s": "1 l"}], previous=previous)

    def run_pipeline(self, root, side_effect):
        config = {"catalog": "catalog.json", "pipeline": ["main.py"], "minimum_products": 1}
        with (patch.object(pipeline, "store_config", return_value=config),
              patch.object(pipeline, "store_dir", return_value=root),
              patch.object(pipeline, "run_step", side_effect=side_effect),
              patch.object(pipeline, "_last_successful_at", return_value="2026-10-07T00:00:00+00:00"),
              patch.object(sys, "argv", ["pipeline", "--country", "nl", "--store", "aldi",
                                         "--soft-fail", "--status-file", str(root / "status.json")])):
            pipeline.main()
        return json.loads((root / "status.json").read_text())

    def test_quality_gate_failure_restores_original_bytes_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = '[{"n": "Last good milk"}]\n'
            (root / "catalog.json").write_text(original)
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                (root / "catalog.json").write_text('[{"n":"Incomplete new milk"}]')
                return 0 if len(calls) == 1 else 1
            result = self.run_pipeline(root, run)
            self.assertIn("finalize_store_catalog.py", " ".join(calls[1]))
            self.assertEqual((root / "catalog.json").read_text(), original)
            self.assertEqual(result["outcome"], "preserved")
            self.assertEqual(result["last_successful_at"], "2026-10-07T00:00:00+00:00")

    def test_unexpected_exception_restores_or_removes_partial_catalog(self):
        for existed in (True, False):
            with self.subTest(existed=existed), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                if existed:
                    (root / "catalog.json").write_text("[]")
                def fail(*args, **kwargs):
                    (root / "catalog.json").write_text('[{"bad":"partial"}]')
                    raise OSError("cannot launch step")
                result = self.run_pipeline(root, fail)
                self.assertEqual(result["outcome"], "preserved")
                if existed:
                    self.assertEqual((root / "catalog.json").read_text(), "[]")
                else:
                    self.assertFalse((root / "catalog.json").exists())
