#!/usr/bin/env python3
"""Publish an explicit availability contract; never serve rejected snapshots."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.paths import all_catalog_paths, catalog_rel_path, store_config
from data_contract import utc_iso
from scripts.catalog_count_policy import count_change_errors
from scripts.finalize_store_catalog import evaluate_catalog
from scripts.workflow_catalog_alerts import baseline_counts


def availability_entry(country: str, store: str, catalog: Path, baseline: dict) -> tuple[dict, dict, dict]:
    health, quality, errors = evaluate_catalog(country, store, catalog)
    if baseline.get("schema_version", 1) >= 2:
        errors.extend(count_change_errors(baseline.get("count", 0), quality["total"]))
    rows = json.loads(catalog.read_text(encoding="utf-8")) if catalog.is_file() else []
    stamps = [utc_iso(row.get("observedAt")) for row in rows if isinstance(row, dict)]
    stamps = [stamp for stamp in stamps if stamp]
    maximum_age = float(store_config(country, store).get("maximum_catalog_age_hours", 48))
    expires = (datetime.fromisoformat(min(stamps)) + timedelta(hours=maximum_age)).isoformat() if stamps else None
    entry = {
        "country": country, "store": store, "available": not errors,
        "reason_codes": errors, "products": quality["total"] if not errors else 0,
        "last_successful_at": max(stamps) if stamps else None,
        "available_until": expires if not errors else None,
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest() if catalog.is_file() else None,
    }
    return entry, health, quality


def main() -> int:
    baselines = baseline_counts()
    stores, health_reports, quality_reports = [], [], []
    for country, store, catalog in all_catalog_paths():
        entry, health, quality = availability_entry(country, store, catalog, baselines.get((country, store), {}))
        if not entry["available"]:
            # Failed candidates from older runners must not replace the recovery
            # snapshot. Git paths come only from the checked-in store allowlist.
            previous = subprocess.run(["git", "show", f"HEAD:{catalog_rel_path(country, store)}"],
                                      cwd=ROOT, capture_output=True, check=False)
            entry["last_successful_at"] = None
            if previous.returncode == 0:
                catalog.write_bytes(previous.stdout)
                entry["catalog_sha256"] = hashlib.sha256(previous.stdout).hexdigest()
                retained = json.loads(previous.stdout)
                stamps = [utc_iso(row.get("observedAt")) for row in retained if isinstance(row, dict)]
                entry["last_successful_at"] = max((stamp for stamp in stamps if stamp), default=None)
            print(f"::warning::{country}/{store} unavailable: " + "; ".join(entry["reason_codes"]))
        stores.append(entry)
        health_reports.append(health)
        quality_reports.append(quality)
    available = sum(row["available"] for row in stores)
    manifest = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"available": available, "unavailable": len(stores) - available},
        "stores": stores,
    }
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (ROOT / "catalog-availability.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (reports / "catalog-health.json").write_text(json.dumps({"stores": health_reports}, indent=2) + "\n")
    # Baselines describe retained files, not rejected candidates.
    from scripts.validate_products import validate_file
    retained_quality = [validate_file(c, s, p) for c, s, p in all_catalog_paths()]
    (ROOT / "data-quality-report.json").write_text(json.dumps(retained_quality, indent=2) + "\n")
    (reports / "candidate-quality.json").write_text(json.dumps(quality_reports, indent=2) + "\n")
    summary = f"Verified fresh stores: {available}/{len(stores)}; unavailable stores are excluded from serving."
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write("\n## Catalog availability\n\n" + summary + "\n\n")
            for row in stores:
                handle.write(f"- {row['country']}/{row['store']}: {'available' if row['available'] else 'unavailable'}\n")
    # A complete outage or broken common extractor still fails the workflow.
    if not available:
        print("No verified fresh store is available; refusing publication", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
