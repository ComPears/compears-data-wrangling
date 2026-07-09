#!/usr/bin/env python3
"""Fail CI when a store output is missing or far below expected size."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Minimum product counts and max drop vs last successful run (50%).
STORE_MINIMUMS: dict[str, tuple[str, int]] = {
    "AH": ("AH/structured_all_merged.json", 8000),
    "ALDI": ("ALDI/structured_aldi.json", 1200),
    "DIRK": ("DIRK/dirk_all.json", 2500),
    "PLUS": ("PLUS/structured_plus.json", 200),
    "LIDL": ("LIDL/lidl_structured.json", 80),
    "COOP": ("COOP/coop_structured.json", 300),
    "JUMBO": ("JUMBO/jumbo_structured.json", 1500),
}

BASELINE_PATH = ROOT / "data-quality-report.json"
MAX_DROP_RATIO = 0.5


def _load_count(rel_path: str) -> int:
    path = ROOT / rel_path
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

    for store, (rel_path, minimum) in STORE_MINIMUMS.items():
        count = _load_count(rel_path)
        print(f"{store}: {count} products ({rel_path})")

        if count < minimum:
            failures.append(
                f"{store}: {count} products < minimum {minimum} ({rel_path})"
            )
            continue

        baseline = baselines.get(store)
        if baseline and baseline > 0:
            drop = (baseline - count) / baseline
            if drop > MAX_DROP_RATIO:
                failures.append(
                    f"{store}: dropped {drop:.0%} vs baseline {baseline} "
                    f"(now {count})"
                )

    if failures:
        print("Store output validation failed:")
        for msg in failures:
            print(f"  - {msg}")
        sys.exit(1)

    print("Store output validation passed.")


if __name__ == "__main__":
    main()
