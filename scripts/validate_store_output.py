#!/usr/bin/env python3
"""Fail CI when a store output is missing or far below expected size."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, catalog_rel_path, load_stores_config, store_config

BASELINE_PATH = ROOT / "data-quality-report.json"
MAX_DROP_RATIO = 0.5


def _load_count(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return len(data) if isinstance(data, list) else 0


def _baseline_counts() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    with open(BASELINE_PATH, encoding="utf-8") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("store")): int(row.get("total") or 0)
        for row in rows
        if isinstance(row, dict) and row.get("store")
    }


def main() -> None:
    baselines = _baseline_counts()
    failures: list[str] = []
    config = load_stores_config()

    for country, slug, catalog in all_catalog_paths():
        count = _load_count(catalog)
        rel = catalog_rel_path(country, slug)
        minimum = int(store_config(country, slug).get("minimum_products") or 0)
        label = f"{country.upper()}/{slug}"
        print(f"{label}: {count} products ({rel})")

        if count < minimum:
            failures.append(f"{label}: {count} products < minimum {minimum} ({rel})")
            continue

        baseline = baselines.get(slug) or baselines.get(label)
        if baseline and baseline > 0:
            drop = (baseline - count) / baseline
            if drop > MAX_DROP_RATIO:
                failures.append(
                    f"{label}: dropped {drop:.0%} vs baseline {baseline} (now {count})"
                )

    if failures:
        print("Store output validation failed:")
        for msg in failures:
            print(f"  - {msg}")
        sys.exit(1)

    print(f"Store output validation passed ({config.get('default_country', 'nl')}).")


if __name__ == "__main__":
    main()
