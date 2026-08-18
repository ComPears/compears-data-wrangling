#!/usr/bin/env python3
"""Fail CI when a store output is missing or far below expected size."""

from __future__ import annotations

import argparse
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


def _baseline_counts() -> dict[str, dict[str, int]]:
    if not BASELINE_PATH.exists():
        return {}
    with open(BASELINE_PATH, encoding="utf-8") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("store")): {
            "count": int(row.get("total") or 0),
            "quality_profile_version": int(row.get("quality_profile_version") or 1),
        }
        for row in rows
        if isinstance(row, dict) and row.get("store")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate store catalog output counts")
    parser.add_argument("--country", default=None, help="Limit to one country (default: all)")
    parser.add_argument("--store", default=None, help="Limit to one store slug")
    args = parser.parse_args()

    baselines = _baseline_counts()
    failures: list[str] = []
    warnings: list[str] = []
    config = load_stores_config()

    targets = all_catalog_paths(args.country)
    if args.store:
        targets = [(c, s, p) for c, s, p in targets if s == args.store]

    for country, slug, catalog in targets:
        count = _load_count(catalog)
        rel = catalog_rel_path(country, slug)
        cfg = store_config(country, slug)
        minimum = int(cfg.get("minimum_products") or 0)
        optional = bool(cfg.get("optional"))
        label = f"{country.upper()}/{slug}"
        print(f"{label}: {count} products ({rel})")

        if count < minimum:
            message = f"{label}: {count} products < minimum {minimum} ({rel})"
            if optional:
                warnings.append(f"{message} [optional]")
            else:
                failures.append(message)
            continue

        baseline_info = baselines.get(slug) or baselines.get(label) or {}
        baseline = int(baseline_info.get("count") or 0)
        baseline_profile = int(baseline_info.get("quality_profile_version") or 1)
        current_profile = int(cfg.get("quality_profile_version") or 1)
        if baseline and baseline_profile != current_profile:
            warnings.append(
                f"{label}: count baseline reset for quality profile migration "
                f"v{baseline_profile} → v{current_profile} ({baseline} to {count})"
            )
        elif baseline > 0:
            drop = (baseline - count) / baseline
            if drop > MAX_DROP_RATIO:
                message = f"{label}: dropped {drop:.0%} vs baseline {baseline} (now {count})"
                if optional:
                    warnings.append(f"{message} [optional]")
                else:
                    failures.append(message)

    for msg in warnings:
        print(f"  warning: {msg}")

    if failures:
        print("Store output validation failed:")
        for msg in failures:
            print(f"  - {msg}")
        sys.exit(1)

    scope = args.country or "all countries"
    print(f"Store output validation passed ({scope}).")


if __name__ == "__main__":
    main()
