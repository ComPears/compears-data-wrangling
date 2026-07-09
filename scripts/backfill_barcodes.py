#!/usr/bin/env python3
"""Add barcode field `b` to structured JSON from image/link fields (no re-scrape)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from barcode_utils import extract_barcode_from_entry

STORE_FILES = [
    "AH/structured_all_merged.json",
    "JUMBO/jumbo_structured.json",
    "ALDI/structured_aldi.json",
    "DIRK/dirk_all.json",
    "LIDL/lidl_structured.json",
    "COOP/coop_structured.json",
    "PLUS/structured_plus.json",
]


def enrich_file(path: Path) -> tuple[int, int]:
    if not path.exists():
        print(f"skip missing {path}")
        return 0, 0

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"skip non-array {path}")
        return 0, 0

    added = 0
    for item in data:
        if item.get("b"):
            continue
        barcode = extract_barcode_from_entry(item)
        if barcode:
            item["b"] = barcode
            added += 1

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ {path.name}: +{added} barcodes ({len(data)} products)")
    return len(data), added


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    total_products = 0
    total_added = 0
    for rel in STORE_FILES:
        count, added = enrich_file(root / rel)
        total_products += count
        total_added += added
    print(f"Done. Added {total_added} barcodes across {total_products} products.")


if __name__ == "__main__":
    main()
