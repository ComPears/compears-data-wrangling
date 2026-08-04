#!/usr/bin/env python3
"""Re-enrich AH raw category files with detail GTINs, then rebuild structured catalog."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ah_api_client import (  # noqa: E402
    DEFAULT_DETAIL_ENRICH_LIMIT,
    enrich_raw_entries_with_detail_barcodes,
    get_anonymous_token,
)
from barcode_utils import normalize_barcode  # noqa: E402

RAW_DIR = ROOT / "countries" / "nl" / "albert-heijn" / "new_results"
AH_DIR = ROOT / "countries" / "nl" / "albert-heijn"


def main() -> int:
    limit = int(os.environ.get("AH_DETAIL_ENRICH_LIMIT", str(DEFAULT_DETAIL_ENRICH_LIMIT)))
    token = get_anonymous_token()
    total_added = 0
    files = sorted(RAW_DIR.glob("*.json"))
    if not files:
        print("No AH raw category files in", RAW_DIR)
        return 1

    for path in files:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            continue
        before = sum(1 for r in rows if isinstance(r, dict) and normalize_barcode(r.get("barcode") or r.get("b")))
        added = enrich_raw_entries_with_detail_barcodes(token, rows, limit=limit)
        after = sum(1 for r in rows if isinstance(r, dict) and normalize_barcode(r.get("barcode") or r.get("b")))
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{path.name}: +{added} (barcodes {before} → {after})")
        total_added += added

    print(f"Total enrichment writes: {total_added}")
    print("Rebuilding structured catalog via AH pipeline structure steps…")
    # Run remaining AH pipeline from merge onward if present
    import subprocess

    for step in ("merge.py", "struc.py", "clean_ah.py"):
        script = AH_DIR / step
        if not script.exists():
            print("skip missing", step)
            continue
        print("===", step)
        subprocess.run([sys.executable, str(script)], cwd=str(AH_DIR), check=False)

    catalog = AH_DIR / "structured_all_merged.json"
    data = json.loads(catalog.read_text(encoding="utf-8"))
    n = len(data)
    b = sum(1 for r in data if isinstance(r, dict) and normalize_barcode(r.get("b")))
    print(f"AH catalog barcode coverage: {b}/{n} = {b/n if n else 0:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
