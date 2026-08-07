from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import workflow_catalog_alerts as alerts


class WorkflowCatalogAlertsTests(unittest.TestCase):
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

    def test_preserved_scrape_status_clears_staleness(self):
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
                patch.object(alerts, "last_change_epoch", return_value=0),
                patch.object(sys, "argv", ["workflow_catalog_alerts.py"]),
            ):
                code = alerts.main()

            self.assertEqual(code, 0)

if __name__ == "__main__":
    unittest.main()
