#!/usr/bin/env python3
"""Validate canonical JSON and emit a data-quality report."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from product_sanitize import should_reject_name

STORE_FILES = [
    ("AH", "AH/structured_all_merged.json"),
    ("JUMBO", "JUMBO/jumbo_structured.json"),
    ("ALDI", "ALDI/structured_aldi.json"),
    ("DIRK", "DIRK/dirk_all.json"),
    ("LIDL", "LIDL/lidl_structured.json"),
    ("COOP", "COOP/coop_structured.json"),
    ("PLUS", "PLUS/structured_plus.json"),
]


def validate_file(store: str, rel_path: str) -> dict:
    path = ROOT / rel_path
    report = {
        "store": store,
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
    if not path.exists():
        return report

    with open(path, encoding="utf-8") as f:
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
    reports = [validate_file(store, rel) for store, rel in STORE_FILES]
    out_path = ROOT / "data-quality-report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2)

    print("| Store | Total | Barcode | Identity | Brand | Weight | Promo in name | Dup ik |")
    print("|-------|------:|--------:|---------:|------:|-------:|--------------:|-------:|")
    for r in reports:
        total = r["total"] or 1
        bc_pct = f"{100 * r['with_barcode'] / total:.0f}%"
        print(
            f"| {r['store']} | {r['total']} | {r['with_barcode']} ({bc_pct}) | "
            f"{r['with_identity']} | {r['with_brand']} | {r['with_weight']} | "
            f"{r['promo_in_name']} | {r['duplicate_identity']} |"
        )

    # Fail CI if Lidl still has promo junk after sanitize
    lidl = next((r for r in reports if r["store"] == "LIDL"), None)
    if lidl and lidl["promo_in_name"] > 0:
        print(f"ERROR: LIDL has {lidl['promo_in_name']} promo-in-name rows after sanitize")
        sys.exit(1)


if __name__ == "__main__":
    main()
