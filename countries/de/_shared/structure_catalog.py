"""Shared structure step: raw JSON → sanitized seed catalog."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parent
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from de_product import structure_raw_products  # noqa: E402

# Ensure repo root on path for category_utils / product_sanitize
_root = SHARED
for _ in range(6):
    if (_root / "config" / "stores.json").is_file():
        root_s = str(_root)
        if root_s not in sys.path:
            sys.path.insert(0, root_s)
        break
    _root = _root.parent


def structure_file(raw_path: Path, catalog_path: Path) -> int:
    if raw_path.is_file():
        with open(raw_path, encoding="utf-8") as handle:
            raw = json.load(handle)
    else:
        raw = []
    if not isinstance(raw, list):
        raw = []
    structured = structure_raw_products(raw)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    with open(catalog_path, "w", encoding="utf-8") as handle:
        json.dump(structured, handle, indent=2, ensure_ascii=False)
    print(f"Structured {len(structured)} products → {catalog_path}")
    return len(structured)
