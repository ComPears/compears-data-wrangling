#!/usr/bin/env python3
"""Drop Coop rows that already exist in the PLUS catalog.

Coop scrapes the same PLUS PLP API via redirects. When both catalogs contain
the same product, keep PLUS as the authoritative listing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import catalog_path


def _match_keys(entries: list[dict]) -> tuple[set[str], set[str], set[str]]:
    identity_keys: set[str] = set()
    barcodes: set[str] = set()
    canonical_names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ik = entry.get("ik")
        if isinstance(ik, str) and ik:
            identity_keys.add(ik)
        barcode = entry.get("b")
        if isinstance(barcode, str) and barcode:
            barcodes.add(barcode)
        canonical = entry.get("cn")
        if isinstance(canonical, str) and canonical:
            canonical_names.add(canonical)
    return identity_keys, barcodes, canonical_names


def _overlaps_plus(entry: dict, plus_ik: set[str], plus_b: set[str], plus_cn: set[str]) -> bool:
    ik = entry.get("ik")
    if isinstance(ik, str) and ik and ik in plus_ik:
        return True
    barcode = entry.get("b")
    if isinstance(barcode, str) and barcode and barcode in plus_b:
        return True
    canonical = entry.get("cn")
    return isinstance(canonical, str) and bool(canonical) and canonical in plus_cn


def dedupe_coop_against_plus(
    country: str = "nl",
    *,
    write: bool = True,
) -> dict[str, int]:
    plus_path = catalog_path(country, "plus")
    coop_path = catalog_path(country, "coop")

    stats = {
        "plus_products": 0,
        "coop_before": 0,
        "coop_after": 0,
        "removed_overlap": 0,
    }

    if not plus_path.exists():
        print(f"skip dedupe: missing PLUS catalog at {plus_path}")
        return stats
    if not coop_path.exists():
        print(f"skip dedupe: missing Coop catalog at {coop_path}")
        return stats

    with open(plus_path, encoding="utf-8") as handle:
        plus_entries = json.load(handle)
    with open(coop_path, encoding="utf-8") as handle:
        coop_entries = json.load(handle)

    if not isinstance(plus_entries, list) or not isinstance(coop_entries, list):
        print("skip dedupe: catalogs are not JSON arrays")
        return stats

    plus_ik, plus_b, plus_cn = _match_keys(plus_entries)
    stats["plus_products"] = len(plus_entries)
    stats["coop_before"] = len(coop_entries)

    kept: list[dict] = []
    removed = 0
    for entry in coop_entries:
        if not isinstance(entry, dict):
            removed += 1
            continue
        if _overlaps_plus(entry, plus_ik, plus_b, plus_cn):
            removed += 1
            continue
        kept.append(entry)

    stats["removed_overlap"] = removed
    stats["coop_after"] = len(kept)

    if write:
        with open(coop_path, "w", encoding="utf-8") as handle:
            json.dump(kept, handle, indent=2, ensure_ascii=False)

    print(
        "✅ coop dedupe vs plus: "
        f"{stats['coop_before']} → {stats['coop_after']} kept, "
        f"{stats['removed_overlap']} overlap removed "
        f"(plus={stats['plus_products']})"
    )
    return stats


def main() -> None:
    stats = dedupe_coop_against_plus()
    if stats["coop_before"] and stats["coop_after"] == 0:
        print("warning: Coop catalog is empty after PLUS dedupe")


if __name__ == "__main__":
    main()
