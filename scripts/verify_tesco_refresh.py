#!/usr/bin/env python3
"""Run all 80 Tesco searches and verify fresh output in a DISPOSABLE checkout.

Uses the production pipeline and publish validators. Never run against catalogs
you want to preserve: a successful scrape and sanitization replace Tesco files.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.paths import catalog_rel_path
from scrape_utils import write_json_atomic
from scripts.catalog_health import analyze_catalog
from scripts.sanitize_all_stores import sanitize_file


def refresh_failures(status: dict, diagnostics: dict, expected_queries: int = 80) -> list[str]:
    failures = []
    if status.get("outcome") != "refreshed":
        failures.append("Tesco did not refresh; a preserved catalog is not a successful test")
    queries = diagnostics.get("queries", [])
    if len(queries) != expected_queries:
        failures.append(f"Only {len(queries)}/{expected_queries} searches completed")
    if any(row.get("state") not in {"products", "no_results"} or row.get("error_type") for row in queries):
        failures.append("Searches include blocking, HTTP, extraction or navigation failures")
    if any(row.get("expected_location") is False for row in queries):
        failures.append("A search ended at an unexpected location")
    return failures


def main() -> int:
    env = os.environ.copy()
    env.update({
        "UK_MAX_QUERIES": "80", "UK_MAX_BLOCKED_QUERIES": "3",
        "UK_MAX_EMPTY_QUERIES": "5",
        "UK_DIAGNOSTICS_DIR": str(ROOT / "artifacts/search-diagnostics"),
    })
    status_path = ROOT / "artifacts/tesco-status.json"
    # Do not soft-fail here: this is verification, not last-good publication.
    result = subprocess.run([
        sys.executable, "scripts/run_store_pipeline.py", "--country", "uk",
        "--store", "tesco", "--status-file", str(status_path),
    ], cwd=ROOT, env=env, check=False)
    if result.returncode:
        return result.returncode
    status = json.loads(status_path.read_text())
    diagnostics = json.loads((ROOT / "artifacts/search-diagnostics/tesco-search.json").read_text())
    failures = refresh_failures(status, diagnostics)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    relative = catalog_rel_path("uk", "tesco")
    sanitize_file("uk", "tesco", relative, observed_at=status["last_successful_at"])
    counts = subprocess.run([
        sys.executable, "scripts/validate_store_output.py", "--country", "uk", "--store", "tesco",
    ], cwd=ROOT, check=False)
    health = analyze_catalog("uk", "tesco", ROOT / relative)
    write_json_atomic(ROOT / "artifacts/tesco-health.json", health)
    print(json.dumps(health, indent=2))
    if counts.returncode or health["status"] == "error":
        return 1
    print("PASS: all 80 searches completed and the fresh Tesco catalog passed count and health gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
