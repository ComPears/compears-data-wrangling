#!/usr/bin/env python3
"""Validate canonical JSON and emit a data-quality report."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, catalog_rel_path
from product_sanitize import should_reject_name


def validate_file(country: str, slug: str, catalog: Path) -> dict:
    rel_path = catalog_rel_path(country, slug)
    report = {
        "country": country,
        "store": slug,
        "total": 0,
        "with_barcode": 0,
        "with_identity": 0,
        "with_brand": 0,
        "with_weight": 0,
        "promo_in_name": 0,
        "missing_price": 0,
        "missing_url": 0,
        "duplicate_identity": 0,
    }
    if not catalog.exists():
        return report

    with open(catalog, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return report

    report["total"] = len(data)
    identity_counts: Counter[str] = Counter()

    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("n") or "")
        if should_reject_name(name):
            report["promo_in_name"] += 1
        price = str(entry.get("p") or "").strip()
        if not price or price in {"0", "0.0", "0.00"}:
            report["missing_price"] += 1
        if not (entry.get("l") or entry.get("i")):
            report["missing_url"] += 1
        if entry.get("b"):
            report["with_barcode"] += 1
        if entry.get("ik"):
            report["with_identity"] += 1
            identity_counts[str(entry["ik"])] += 1
        if entry.get("bn"):
            report["with_brand"] += 1
        if entry.get("wg"):
            report["with_weight"] += 1

    report["duplicate_identity"] = sum(c - 1 for c in identity_counts.values() if c > 1)
    return report


def main() -> None:
    reports = []
    for country, slug, catalog in all_catalog_paths():
        reports.append(validate_file(country, slug, catalog))

    out_path = ROOT / "data-quality-report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2)

    print("| Country | Store | Total | Barcode | Identity | Brand | Weight | Promo | Dup ik |")
    print("|---------|-------|------:|--------:|---------:|------:|-------:|------:|-------:|")
    for r in reports:
        total = r["total"] or 1
        bc_pct = f"{100 * r['with_barcode'] / total:.0f}%"
        print(
            f"| {r['country']} | {r['store']} | {r['total']} | {r['with_barcode']} ({bc_pct}) | "
            f"{r['with_identity']} | {r['with_brand']} | {r['with_weight']} | "
            f"{r['promo_in_name']} | {r['duplicate_identity']} |"
        )

    lidl = next((r for r in reports if r["store"] == "lidl"), None)
    if lidl and lidl["promo_in_name"] > 0:
        print(f"ERROR: LIDL has {lidl['promo_in_name']} promo-in-name rows after sanitize")
        sys.exit(1)


if __name__ == "__main__":
    main()
