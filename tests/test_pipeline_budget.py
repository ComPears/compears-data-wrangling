import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_store_pipeline as pipeline


class PipelineBudgetTests(unittest.TestCase):
    def test_timeout_stops_child_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "should-not-exist"
            child = "import time,pathlib; time.sleep(1); pathlib.Path(%r).touch()" % str(marker)
            command = [sys.executable, "-c",
                       "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',%r]); time.sleep(30)" % child]
            self.assertEqual(pipeline.run_step(command, cwd=Path(tmp), timeout=0.2), 124)
            import time
            time.sleep(1.1)
            self.assertFalse(marker.exists())

    def test_success_and_exhausted_budget(self):
        self.assertEqual(pipeline.run_step([sys.executable, "-c", "pass"], cwd=Path.cwd(), timeout=5), 0)
        self.assertEqual(pipeline.run_step(["not-a-real-command"], cwd=Path.cwd(), timeout=0), 124)

    def test_timeout_rolls_back_catalog_and_writes_honest_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            original = '[{"n":"Milk","observedAt":"2026-09-21T01:00:00Z"}]'
            catalog.write_text(original)
            status = root / "status.json"
            def timed_out(*args, **kwargs):
                catalog.write_text("[]")
                return 124
            with (patch.object(pipeline, "store_config", return_value={"catalog": "catalog.json", "pipeline": ["main.py"], "minimum_products": 1}),
                  patch.object(pipeline, "store_dir", return_value=root),
                  patch.object(pipeline, "run_step", side_effect=timed_out),
                  patch.object(sys, "argv", ["pipeline", "--country", "nl", "--store", "plus", "--soft-fail", "--status-file", str(status)])):
                pipeline.main()
            self.assertEqual(catalog.read_text(), original)
            result = json.loads(status.read_text())
            self.assertEqual(result["outcome"], "preserved")
            self.assertIn("budget exhausted", result["reason"])
            self.assertEqual(result["last_successful_at"], "2026-09-21T01:00:00+00:00")

    def test_daily_plus_skips_optional_enrichment_and_logs_progress(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/update_stores.yaml").read_text()
        self.assertIn("PLUS_PDP_ENRICH_LIMIT: '0'", workflow)
        self.assertIn("PYTHONUNBUFFERED: '1'", workflow)
        self.assertIn("--timeout-seconds 3600", workflow)
