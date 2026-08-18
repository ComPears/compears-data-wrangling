from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import workflow_catalog_alerts as alerts


class WorkflowCatalogAlertsTests(unittest.TestCase):
    def test_store_specific_hard_age_warns_before_it_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "countries" / "uk" / "tesco" / "tesco_structured.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([{"cn": "milk", "p": "1.00"}]), encoding="utf-8")
            seventy_two_hours_ago = int(__import__("time").time() - (72 * 3600))

            with (
                patch.object(alerts, "ROOT", root),
                patch.object(alerts, "SCRAPE_STATUS_DIR", root / "missing"),
                patch.object(alerts, "all_catalog_paths", return_value=[("uk", "tesco", catalog)]),
                patch.object(alerts, "catalog_rel_path", return_value=str(catalog.relative_to(root))),
                patch.object(
                    alerts,
                    "store_config",
                    return_value={
                        "minimum_products": 1,
                        "optional": False,
                        "maximum_catalog_age_hours": 168,
                    },
                ),
                patch.object(alerts, "baseline_counts", return_value={}),
                patch.object(alerts, "last_change_epoch", return_value=seventy_two_hours_ago),
                patch.object(
                    sys,
                    "argv",
                    ["workflow_catalog_alerts.py", "--max-age-hours", "48"],
                ),
            ):
                code = alerts.main()

        self.assertEqual(code, 0)

    def test_schema_v2_count_regression_blocks_required_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "countries" / "uk" / "tesco" / "tesco_structured.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([{"cn": "milk", "p": "1.00"}]), encoding="utf-8")

            with (
                patch.object(alerts, "ROOT", root),
                patch.object(alerts, "SCRAPE_STATUS_DIR", root / "missing"),
                patch.object(alerts, "all_catalog_paths", return_value=[("uk", "tesco", catalog)]),
                patch.object(alerts, "catalog_rel_path", return_value=str(catalog.relative_to(root))),
                patch.object(alerts, "store_config", return_value={"minimum_products": 1}),
                patch.object(
                    alerts,
                    "baseline_counts",
                    return_value={("uk", "tesco"): {"count": 10, "schema_version": 2}},
                ),
                patch.object(alerts, "last_change_epoch", return_value=int(__import__("time").time())),
                patch.object(sys, "argv", ["workflow_catalog_alerts.py"]),
            ):
                code = alerts.main()

        self.assertEqual(code, 1)

    def test_first_schema_v2_migration_resets_count_baseline_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "countries" / "nl" / "lidl" / "lidl_structured.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([{"cn": "milk", "p": "1.00"}]), encoding="utf-8")

            with (
                patch.object(alerts, "ROOT", root),
                patch.object(alerts, "SCRAPE_STATUS_DIR", root / "missing"),
                patch.object(alerts, "all_catalog_paths", return_value=[("nl", "lidl", catalog)]),
                patch.object(alerts, "catalog_rel_path", return_value=str(catalog.relative_to(root))),
                patch.object(alerts, "store_config", return_value={"minimum_products": 1}),
                patch.object(
                    alerts,
                    "baseline_counts",
                    return_value={("nl", "lidl"): {"count": 10, "schema_version": 1}},
                ),
                patch.object(alerts, "last_change_epoch", return_value=int(__import__("time").time())),
                patch.object(sys, "argv", ["workflow_catalog_alerts.py"]),
            ):
                code = alerts.main()

        self.assertEqual(code, 0)

    def test_optional_store_staleness_is_warning_not_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "countries" / "nl" / "coop" / "coop_structured.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([{"cn": "milk", "p": "1.00"}]), encoding="utf-8")

            def fake_store_config(_country: str, store: str) -> dict:
                return {
                    "minimum_products": 1,
                    "optional": store == "coop",
                }

            with (
                patch.object(alerts, "ROOT", root),
                patch.object(alerts, "BASELINE_PATH", root / "missing.json"),
                patch.object(alerts, "SCRAPE_STATUS_DIR", root / "reports" / "scrape-status"),
                patch.object(
                    alerts,
                    "all_catalog_paths",
                    return_value=[("nl", "coop", catalog)],
                ),
                patch.object(alerts, "catalog_rel_path", return_value=str(catalog.relative_to(root))),
                patch.object(alerts, "store_config", side_effect=fake_store_config),
                patch.object(alerts, "last_change_epoch", return_value=0),
                patch.object(sys, "argv", ["workflow_catalog_alerts.py"]),
            ):
                code = alerts.main()

            self.assertEqual(code, 0)

    def test_required_store_staleness_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "countries" / "nl" / "plus" / "structured_plus.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([{"cn": "milk", "p": "1.00"}]), encoding="utf-8")

            def fake_store_config(_country: str, _store: str) -> dict:
                return {"minimum_products": 1, "optional": False}

            with (
                patch.object(alerts, "ROOT", root),
                patch.object(alerts, "BASELINE_PATH", root / "missing.json"),
                patch.object(alerts, "SCRAPE_STATUS_DIR", root / "reports" / "scrape-status"),
                patch.object(
                    alerts,
                    "all_catalog_paths",
                    return_value=[("nl", "plus", catalog)],
                ),
                patch.object(alerts, "catalog_rel_path", return_value=str(catalog.relative_to(root))),
                patch.object(alerts, "store_config", side_effect=fake_store_config),
                patch.object(alerts, "last_change_epoch", return_value=0),
                patch.object(sys, "argv", ["workflow_catalog_alerts.py"]),
            ):
                code = alerts.main()

            self.assertEqual(code, 1)

    def test_optional_store_below_minimum_is_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "countries" / "de" / "rewe" / "rewe_structured.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(
                json.dumps([{"cn": f"item-{i}", "p": "1.00"} for i in range(10)]),
                encoding="utf-8",
            )

            def fake_store_config(_country: str, _store: str) -> dict:
                return {"minimum_products": 80, "optional": True}

            with (
                patch.object(alerts, "ROOT", root),
                patch.object(alerts, "BASELINE_PATH", root / "missing.json"),
                patch.object(alerts, "SCRAPE_STATUS_DIR", root / "reports" / "scrape-status"),
                patch.object(
                    alerts,
                    "all_catalog_paths",
                    return_value=[("de", "rewe", catalog)],
                ),
                patch.object(alerts, "catalog_rel_path", return_value=str(catalog.relative_to(root))),
                patch.object(alerts, "store_config", side_effect=fake_store_config),
                patch.object(alerts, "last_change_epoch", return_value=int(__import__("time").time())),
                patch.object(sys, "argv", ["workflow_catalog_alerts.py"]),
            ):
                code = alerts.main()

            self.assertEqual(code, 0)

    def test_warn_only_never_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "countries" / "nl" / "plus" / "structured_plus.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([{"cn": "milk", "p": "1.00"}]), encoding="utf-8")

            def fake_store_config(_country: str, _store: str) -> dict:
                return {"minimum_products": 1, "optional": False}

            with (
                patch.object(alerts, "ROOT", root),
                patch.object(alerts, "BASELINE_PATH", root / "missing.json"),
                patch.object(alerts, "SCRAPE_STATUS_DIR", root / "reports" / "scrape-status"),
                patch.object(
                    alerts,
                    "all_catalog_paths",
                    return_value=[("nl", "plus", catalog)],
                ),
                patch.object(alerts, "catalog_rel_path", return_value=str(catalog.relative_to(root))),
                patch.object(alerts, "store_config", side_effect=fake_store_config),
                patch.object(alerts, "last_change_epoch", return_value=0),
                patch.object(sys, "argv", ["workflow_catalog_alerts.py", "--warn-only"]),
            ):
                code = alerts.main()

            self.assertEqual(code, 0)

    def test_preserved_scrape_status_does_not_clear_staleness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "countries" / "uk" / "tesco" / "tesco_structured.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([{"cn": "milk", "p": "1.00"}]), encoding="utf-8")
            status_dir = root / "reports" / "scrape-status"
            status_dir.mkdir(parents=True)
            (status_dir / "uk-tesco.json").write_text(
                json.dumps(
                    {
                        "country": "uk",
                        "store": "tesco",
                        "outcome": "preserved",
                        "timestamp": "2026-08-05T03:00:00+00:00",
                        "final": 1,
                    }
                ),
                encoding="utf-8",
            )

            def fake_store_config(_country: str, _store: str) -> dict:
                return {"minimum_products": 1, "optional": False}

            with (
                patch.object(alerts, "ROOT", root),
                patch.object(alerts, "BASELINE_PATH", root / "missing.json"),
                patch.object(alerts, "SCRAPE_STATUS_DIR", status_dir),
                patch.object(
                    alerts,
                    "all_catalog_paths",
                    return_value=[("uk", "tesco", catalog)],
                ),
                patch.object(alerts, "catalog_rel_path", return_value=str(catalog.relative_to(root))),
                patch.object(alerts, "store_config", side_effect=fake_store_config),
                patch.object(
                    alerts,
                    "last_change_epoch",
                    return_value=int(__import__("time").time()),
                ),
                patch.object(sys, "argv", ["workflow_catalog_alerts.py"]),
            ):
                code = alerts.main()

            self.assertEqual(code, 1)

    def test_preserved_catalog_uses_real_last_successful_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "countries" / "uk" / "tesco" / "tesco_structured.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([{"cn": "milk", "p": "1.00"}]), encoding="utf-8")
            status_dir = root / "reports" / "scrape-status"
            status_dir.mkdir(parents=True)
            (status_dir / "uk-tesco.json").write_text(
                json.dumps(
                    {
                        "country": "uk",
                        "store": "tesco",
                        "outcome": "preserved",
                        "attempted_at": "2026-08-05T03:00:00+00:00",
                        "last_successful_at": datetime.now(timezone.utc).isoformat(),
                        "final": 1,
                    }
                ),
                encoding="utf-8",
            )

            def fake_store_config(_country: str, _store: str) -> dict:
                return {"minimum_products": 1, "optional": False}

            with (
                patch.object(alerts, "ROOT", root),
                patch.object(alerts, "BASELINE_PATH", root / "missing.json"),
                patch.object(alerts, "SCRAPE_STATUS_DIR", status_dir),
                patch.object(
                    alerts,
                    "all_catalog_paths",
                    return_value=[("uk", "tesco", catalog)],
                ),
                patch.object(alerts, "catalog_rel_path", return_value=str(catalog.relative_to(root))),
                patch.object(alerts, "store_config", side_effect=fake_store_config),
                patch.object(alerts, "last_change_epoch", return_value=0),
                patch.object(sys, "argv", ["workflow_catalog_alerts.py"]),
            ):
                code = alerts.main()

            self.assertEqual(code, 0)

if __name__ == "__main__":
    unittest.main()
