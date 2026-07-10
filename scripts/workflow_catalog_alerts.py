#!/usr/bin/env python3
"""Emit GitHub Actions alerts for missing, suspicious, or stale catalogs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_HINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_HINT))

from config.paths import ROOT, all_catalog_paths, catalog_rel_path, store_config

BASELINE_PATH = ROOT / "data-quality-report.json"


def baseline_counts() -> dict[tuple[str, str], int]:
    if not BASELINE_PATH.exists():
        return {}
    with open(BASELINE_PATH, encoding="utf-8") as handle:
        rows = json.load(handle)
    return {
        (str(row.get("country") or "nl"), str(row["store"])): int(row.get("total") or 0)
        for row in rows
        if isinstance(row, dict) and row.get("store")
    }


def catalog_count(path: Path) -> tuple[int, str | None]:
    if not path.exists():
        return 0, "catalog file is missing"
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        return 0, f"catalog is unreadable: {error}"
    if not isinstance(data, list):
        return 0, "catalog root is not a JSON array"
    return len(data), None


def last_change_epoch(path: Path) -> int:
    relative = str(path.relative_to(ROOT))
    changed = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", relative],
        cwd=ROOT,
        check=False,
    ).returncode != 0
    if changed:
        return int(time.time())

    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", relative],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip().isdigit():
        return int(result.stdout.strip())
    return int(path.stat().st_mtime) if path.exists() else 0


def annotation(level: str, path: str, message: str) -> None:
    safe_message = message.replace("\n", " ")
    print(f"::{level} file={path}::{safe_message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", default=None)
    parser.add_argument("--store", default=None)
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=float(os.getenv("CATALOG_MAX_AGE_HOURS", "72")),
    )
    parser.add_argument(
        "--max-drop-ratio",
        type=float,
        default=float(os.getenv("CATALOG_MAX_DROP_RATIO", "0.5")),
    )
    parser.add_argument(
        "--max-growth-ratio",
        type=float,
        default=float(os.getenv("CATALOG_MAX_GROWTH_RATIO", "3")),
    )
    args = parser.parse_args()

    targets = all_catalog_paths(args.country)
    if args.store:
        targets = [(country, store, path) for country, store, path in targets if store == args.store]
    baselines = baseline_counts()
    failures: list[str] = []
    summary = ["## Catalog monitoring", "", "| Catalog | Products | Age | Result |", "|---|---:|---:|---|"]

    for country, store, path in targets:
        relative = catalog_rel_path(country, store)
        count, read_error = catalog_count(path)
        minimum = int(store_config(country, store).get("minimum_products") or 0)
        baseline = baselines.get((country, store), 0)
        changed_at = last_change_epoch(path)
        age_hours = (time.time() - changed_at) / 3600 if changed_at else float("inf")
        issues: list[str] = []

        if read_error:
            issues.append(read_error)
        elif count == 0:
            issues.append("catalog contains zero products")
        elif count < minimum:
            issues.append(f"{count} products is below configured minimum {minimum}")

        if baseline > 0 and count < baseline * (1 - args.max_drop_ratio):
            issues.append(
                f"count dropped from baseline {baseline} to {count} "
                f"(limit {args.max_drop_ratio:.0%})"
            )
        if baseline > 0 and count > baseline * args.max_growth_ratio:
            issues.append(
                f"count grew from baseline {baseline} to {count} "
                f"(limit {args.max_growth_ratio:g}x)"
            )
        if age_hours > args.max_age_hours:
            issues.append(
                f"catalog has not changed for {age_hours:.1f}h "
                f"(limit {args.max_age_hours:g}h)"
            )

        result = "OK" if not issues else "; ".join(issues)
        summary.append(f"| `{country}/{store}` | {count} | {age_hours:.1f}h | {result} |")
        for issue in issues:
            message = f"{country}/{store}: {issue}. Check the store scraper logs and rerun this workflow."
            annotation("error", relative, message)
            failures.append(message)

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(summary) + "\n")

    if failures:
        print(f"Catalog monitoring failed with {len(failures)} actionable alert(s).")
        return 1
    print(f"Catalog monitoring passed for {len(targets)} catalog(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
