#!/usr/bin/env python3
"""Dry-run every catalog through schema v2 without changing source files."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, country_config, store_config
from product_sanitize import dedupe_by_identity, sanitize_entry_with_reason
from scripts.build_match_index import build_country_from_catalogs
from scripts.catalog_health import analyze_catalog


def preview_catalog(
    country: str,
    store: str,
    source: Path,
    *,
    observed_at: str,
    output_dir: Path,
) -> dict:
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "country": country,
            "store": store,
            "input": 0,
            "kept": 0,
            "error": str(error),
            "health": {"status": "error", "issues": [{"code": "catalog_unreadable"}]},
        }
    rows = payload if isinstance(payload, list) else []
    currency = str(country_config(country).get("currency") or "")
    cleaned: list[dict] = []
    reasons: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            reasons["malformed_row"] += 1
            continue
        offer, reason = sanitize_entry_with_reason(
            row,
            country=country,
            store=store,
            currency=currency,
            observed_at=observed_at,
        )
        if offer is None:
            reasons[reason or "unknown"] += 1
        else:
            cleaned.append(offer)
    cleaned, duplicate_count = dedupe_by_identity(cleaned)
    preview_path = output_dir / f"{country}-{store}.json"
    preview_path.write_text(json.dumps(cleaned, ensure_ascii=False), encoding="utf-8")
    health = analyze_catalog(
        country,
        store,
        preview_path,
        now=datetime.fromisoformat(observed_at.replace("Z", "+00:00")),
    )
    return {
        "country": country,
        "store": store,
        "optional": bool(store_config(country, store).get("optional")),
        "minimum_products": int(store_config(country, store).get("minimum_products") or 0),
        "input": len(rows),
        "kept": len(cleaned),
        "rejected": sum(reasons.values()),
        "deduplicated": duplicate_count,
        "rejection_reasons": dict(reasons.most_common()),
        "health": health,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "contract-migration-preview.json",
    )
    parser.add_argument("--observed-at", default=datetime.now(timezone.utc).isoformat())
    args = parser.parse_args()

    observed = datetime.fromisoformat(args.observed_at.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    observed_at = observed.astimezone(timezone.utc).isoformat()

    with tempfile.TemporaryDirectory(prefix="compears-contract-preview-") as tmp:
        output_dir = Path(tmp)
        stores = [
            preview_catalog(
                country,
                store,
                catalog,
                observed_at=observed_at,
                output_dir=output_dir,
            )
            for country, store, catalog in all_catalog_paths()
        ]
        match_quality = []
        for country in sorted({str(row["country"]) for row in stores}):
            catalogs = [
                (str(row["store"]), output_dir / f"{country}-{row['store']}.json")
                for row in stores
                if row["country"] == country
            ]
            _matches, quality = build_country_from_catalogs(country, catalogs)
            match_quality.append(quality)

    failures = [
        row
        for row in stores
        if not row.get("optional")
        and (
            int(row.get("kept") or 0) < int(row.get("minimum_products") or 0)
            or row.get("health", {}).get("status") == "error"
        )
    ]
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "simulatedObservedAt": observed_at,
        "summary": {
            "stores": len(stores),
            "requiredFailures": len(failures),
            "input": sum(int(row.get("input") or 0) for row in stores),
            "kept": sum(int(row.get("kept") or 0) for row in stores),
            "rejected": sum(int(row.get("rejected") or 0) for row in stores),
            "deduplicated": sum(int(row.get("deduplicated") or 0) for row in stores),
            "comparableOffers": sum(int(row["matchedOffers"]) for row in match_quality),
            "comparisonGroups": sum(int(row["groups"]) for row in match_quality),
        },
        "matchQuality": match_quality,
        "stores": stores,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("Country  Store             Input    Kept  Rejected  Health")
    for row in stores:
        print(
            f"{row['country']:<8} {row['store']:<16} {row.get('input', 0):>7} "
            f"{row.get('kept', 0):>7} {row.get('rejected', 0):>9}  "
            f"{row.get('health', {}).get('status', 'error')}"
        )
    print(json.dumps(report["summary"], indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
