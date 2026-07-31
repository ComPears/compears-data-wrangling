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


if __name__ == "__main__":
    unittest.main()
