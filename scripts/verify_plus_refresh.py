#!/usr/bin/env python3
"""Full live PLUS verification. Run only in a disposable checkout.

Uses the daily pipeline's 3600-second budget, no optional PDP enrichment, all
configured categories, and publish count/health validators. A preserved catalog
or incomplete category is a failed test, even if a wrapper returned exit zero.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.paths import catalog_rel_path
from scrape_utils import write_json_atomic
from scripts.catalog_health import analyze_catalog
from scripts.sanitize_all_stores import sanitize_file


def refresh_failures(status, diagnostics, expected_urls):
    failures = []
    if status.get("outcome") != "refreshed":
        failures.append("PLUS did not refresh; preserved data is not a successful test")
    if [row.get("url") for row in diagnostics] != expected_urls:
        failures.append("PLUS did not attempt every configured category exactly once")
    if any(row.get("state") != "complete" for row in diagnostics):
        failures.append("PLUS has incomplete categories")
    return failures


def main():
    start = time.monotonic()
    status_path = ROOT / "artifacts/plus-status.json"
    result = subprocess.run([
        sys.executable, "scripts/run_store_pipeline.py", "--country", "nl",
        "--store", "plus", "--timeout-seconds", "3600", "--status-file", str(status_path),
    ], cwd=ROOT, env={**os.environ, "PLUS_PDP_ENRICH_LIMIT": "0", "PYTHONUNBUFFERED": "1"}, check=False)
    if result.returncode:
        return result.returncode
    status = json.loads(status_path.read_text())
    diagnostics = json.loads((ROOT / "artifacts/plus-categories.json").read_text())
    spec = importlib.util.spec_from_file_location("plus_links", ROOT / "countries/nl/plus/links.py")
    links = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(links)
    failures = refresh_failures(status, diagnostics, links.links)
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    relative = catalog_rel_path("nl", "plus")
    sanitize_file("nl", "plus", relative, observed_at=status["last_successful_at"])
    counts = subprocess.run([
        sys.executable, "scripts/validate_store_output.py", "--country", "nl", "--store", "plus",
    ], cwd=ROOT, check=False)
    health = analyze_catalog("nl", "plus", ROOT / relative)
    write_json_atomic(ROOT / "artifacts/plus-health.json", health)
    print(json.dumps(health, indent=2))
    if counts.returncode or health["status"] == "error":
        return 1
    print(f"PASS: {len(links.links)} complete PLUS categories, fresh catalog, count/health gates; "
          f"elapsed {time.monotonic() - start:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
