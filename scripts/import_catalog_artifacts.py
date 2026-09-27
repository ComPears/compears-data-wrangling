#!/usr/bin/env python3
"""Import only configured catalog/status JSON, never executable artifact content."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, catalog_rel_path, store_config
from data_contract import utc_iso
from scripts.catalog_health import analyze_catalog
from scripts.validate_products import validate_file, quantity_coverage_messages

MAX_FILE_BYTES = 50 * 1024 * 1024


def preserved_status(workspace: Path, country: str, store: str) -> bytes:
    """Missing transport is recoverable only with a fresh, validated snapshot.

    Do not change catalog observations or inherit a previous 'refreshed' status.
    Corrupt/present artifacts still fail closed in the normal importer.
    """
    catalog = _contained_path(workspace, Path(catalog_rel_path(country, store)))
    if not catalog.is_file() or catalog.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Missing scraper artifact and usable fallback: {country}/{store}")
    rows = json.loads(catalog.read_bytes())
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"Invalid fallback catalog: {country}/{store}")
    cfg = store_config(country, store)
    report = validate_file(country, store, catalog)
    quantity_failure, _ = quantity_coverage_messages(report, cfg)
    if (len(rows) < int(cfg.get("minimum_products") or 0) or quantity_failure
            or any(report[key] for key in ("missing_price", "contract_errors", "promo_in_name"))
            or analyze_catalog(country, store, catalog)["status"] == "error"):
        raise ValueError(f"Fallback fails data quality: {country}/{store}")
    now = datetime.now(timezone.utc)
    timestamps = [utc_iso(row.get("observedAt")) for row in rows]
    maximum_age = float(cfg.get("maximum_catalog_age_hours", 48))
    for stamp in timestamps:
        age = (now - datetime.fromisoformat(stamp)).total_seconds() / 3600 if stamp else float("inf")
        if not -1 <= age <= maximum_age:
            raise ValueError(f"Fallback is stale or has invalid observation time: {country}/{store}")
    return (json.dumps({
        "country": country, "store": store, "outcome": "preserved",
        "reason": "scraper artifact missing; validated fresh repository snapshot retained",
        "attempted_at": now.isoformat(), "timestamp": now.isoformat(),
        "last_successful_at": max(timestamps), "final": len(rows),
    }, indent=2) + "\n").encode()


def _contained_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Artifact path must be relative and contained")
    candidate = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink is not allowed: {relative}")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes root: {relative}")
    return candidate


def copy_catalog_artifacts(artifact_root: Path, workspace: Path) -> int:
    """Validate the complete batch before overwriting any allowlisted data files."""
    artifact_root = artifact_root.resolve()
    workspace = workspace.resolve()
    planned: list[tuple[Path, bytes]] = []
    stores = all_catalog_paths()
    for country, store, _ in stores:
        artifact_name = Path(f"catalog-{country}-{store}")
        artifact = _contained_path(artifact_root, artifact_name)
        catalog = Path(catalog_rel_path(country, store))
        status = Path("reports/scrape-status") / f"{country}-{store}.json"
        if not artifact.exists():
            payload = preserved_status(workspace, country, store)
            planned.append((_contained_path(workspace, status), payload))
            continue
        if not artifact.is_dir():
            raise ValueError(f"Invalid scraper artifact directory: {artifact_name}")
        allowed = {catalog, status}
        for entry in artifact.rglob("*"):
            relative = entry.relative_to(artifact)
            if entry.is_symlink() or (not entry.is_dir() and relative not in allowed):
                raise ValueError(f"Unexpected artifact entry: {artifact_name / relative}")
        for relative, expected_type in ((catalog, list), (status, dict)):
            source = _contained_path(artifact, relative)
            destination = _contained_path(workspace, relative)
            if not source.is_file():
                raise ValueError(f"Missing artifact file: {artifact_name / relative}")
            if source.stat().st_size > MAX_FILE_BYTES:
                raise ValueError(f"Oversized artifact file: {artifact_name / relative}")
            payload = source.read_bytes()
            value = json.loads(payload)
            if not isinstance(value, expected_type):
                raise ValueError(f"Invalid JSON shape: {artifact_name / relative}")
            planned.append((destination, payload))
    for destination, payload in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    return len(stores)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=ROOT)
    args = parser.parse_args()
    count = copy_catalog_artifacts(args.artifact_root, args.workspace)
    print(f"Imported {count} validated catalog/status artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
