#!/usr/bin/env python3
"""Post-scrape: sanitize, measure barcode coverage, raise CI floors, print seed command."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from barcode_utils import normalize_barcode
from config.paths import catalog_path


TARGET_STORES = ("albert-heijn", "plus", "dirk", "jumbo")


def coverage_for(slug: str) -> float:
    path = catalog_path("nl", slug)
    if not path.exists():
        return 0.0
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        return 0.0
    with_b = 0
    for row in data:
        if not isinstance(row, dict):
            continue
        if normalize_barcode(row.get("b")):
            with_b += 1
    return with_b / len(data)


def propose_floors() -> dict[str, float]:
    proposed: dict[str, float] = {}
    for slug in TARGET_STORES:
        cov = coverage_for(slug)
        # Conservative floor: half of observed coverage, capped, and only if
        # enrichment clearly landed (at least 5% real barcodes in catalog `b`).
        if cov < 0.05:
            proposed[slug] = 0.0
            continue
        floor = min(0.5, math.floor(cov * 50) / 100)  # half, 0.01 steps, max 0.5
        # Keep a small buffer under observed coverage
        floor = min(floor, max(0.05, round(cov * 0.5, 2)))
        proposed[slug] = floor
    return proposed


def patch_catalog_health(floors: dict[str, float]) -> None:
    health = ROOT / "scripts" / "catalog_health.py"
    text = health.read_text(encoding="utf-8")
    start = text.index("BARCODE_FLOORS: dict[str, float] = {")
    end = text.index("}", start) + 1
    lines = ["BARCODE_FLOORS: dict[str, float] = {"]
    for slug, value in floors.items():
        lines.append(f'    "{slug}": {value},')
    lines.append("}")
    new_block = "\n".join(lines)
    health.write_text(text[:start] + new_block + text[end:], encoding="utf-8")


def main() -> int:
    print("Running sanitize_all_stores.py …", flush=True)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sanitize_all_stores.py")],
        cwd=str(ROOT),
        check=False,
    )

    cov = {slug: round(coverage_for(slug), 4) for slug in TARGET_STORES}
    print("Observed NL barcode coverage (`b` field):", json.dumps(cov, indent=2), flush=True)
    floors = propose_floors()
    print("Proposed BARCODE_FLOORS:", json.dumps(floors, indent=2), flush=True)
    if any(v > 0 for v in floors.values()):
        patch_catalog_health(floors)
        print("Updated scripts/catalog_health.py BARCODE_FLOORS", flush=True)
    else:
        print(
            "No floors raised (coverage still <5% for targets). Enrichment may need longer scrapes.",
            flush=True,
        )

    print("Running catalog_health.py …", flush=True)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "catalog_health.py")],
        cwd=str(ROOT),
        check=False,
    )

    print(
        "\nNext: seed backend catalogs:\n"
        "  cd ../backend && COUNTRY=nl,uk,de npm run seed\n",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
