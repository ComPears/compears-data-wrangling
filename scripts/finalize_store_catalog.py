#!/usr/bin/env python3
"""Reject unusable refreshes before the pipeline discards its rollback copy."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.paths import store_config, store_dir
from scripts.catalog_health import analyze_catalog
from scripts.catalog_count_policy import count_change_errors
from scripts.sanitize_all_stores import sanitize_file
from scripts.validate_products import validate_file, quantity_coverage_messages


def evaluate_catalog(country: str, store: str, catalog: Path) -> tuple[dict, dict, list[str]]:
    health = analyze_catalog(country, store, catalog, require_fresh=True)
    quality = validate_file(country, store, catalog)
    errors = [str(issue["code"]) for issue in health["issues"]
              if issue["severity"] == "error"]
    for field in ("missing_price", "contract_errors", "promo_in_name"):
        if quality[field]:
            errors.append(f"{field}: {quality[field]}")
    quantity_error, _ = quantity_coverage_messages(quality, store_config(country, store))
    if quantity_error:
        errors.append(quantity_error)
    if quality["with_observed_at"] != quality["total"]:
        errors.append("missing observation timestamps")
    if not quality["total"]:
        errors.append("empty catalog")
    if country == "uk" and store == "morrisons" and catalog.is_file():
        rows = json.loads(catalog.read_text(encoding="utf-8"))
        # Old ancestor-text extraction could turn 72.6p/litre into a 6p offer.
        # Retained snapshots need a fresh extraction, never a guessed correction.
        if any(row.get("sourceMethod") != "dom_cards_selling_price_v2" for row in rows if isinstance(row, dict)):
            errors.append("unverified_morrisons_selling_price")
    return health, quality, errors


def finalize(country: str, store: str, catalog: Path, previous: Path | None,
             observed_at: str, report_path: Path) -> dict:
    # The caller owns rollback, including exceptions during sanitization.
    stats = sanitize_file(country, store, str(catalog), observed_at=observed_at)
    health, quality, errors = evaluate_catalog(country, store, catalog)
    if previous and previous.is_file():
        rows = json.loads(previous.read_text(encoding="utf-8"))
        # Compare like-for-like canonical snapshots, not legacy schema counts.
        if isinstance(rows, list) and rows and all(
            isinstance(row, dict) and row.get("schemaVersion") == 2 for row in rows
        ):
            errors.extend(count_change_errors(len(rows), quality["total"]))
    result = {"country": country, "store": store, "sanitization": stats,
              "health": health, "quality": quality, "errors": errors}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise ValueError("; ".join(errors))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--previous-catalog", type=Path)
    parser.add_argument("--observed-at", required=True)
    args = parser.parse_args()
    catalog = store_dir(args.country, args.store) / store_config(args.country, args.store)["catalog"]
    report = ROOT / "reports" / "refresh-quality" / f"{args.country}-{args.store}.json"
    try:
        finalize(args.country, args.store, catalog, args.previous_catalog, args.observed_at, report)
    except (OSError, ValueError, TypeError) as error:
        print(f"Refresh rejected for {args.country}/{args.store}: {error}", file=sys.stderr)
        return 1
    print(f"Refresh quality accepted for {args.country}/{args.store}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
