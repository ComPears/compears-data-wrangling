#!/usr/bin/env python3
"""Emit GitHub Actions alerts for missing, suspicious, or stale catalogs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_HINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_HINT))

from config.paths import ROOT, all_catalog_paths, catalog_rel_path, store_config

BASELINE_PATH = ROOT / "data-quality-report.json"
SCRAPE_STATUS_DIR = ROOT / "reports" / "scrape-status"


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


def scrape_outcomes(status_dir: Path | None = None) -> dict[tuple[str, str], dict]:
    outcomes: dict[tuple[str, str], dict] = {}
    directory = SCRAPE_STATUS_DIR if status_dir is None else status_dir
    if not directory.is_dir():
        return outcomes
    for path in directory.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        country = str(payload.get("country") or "")
        store = str(payload.get("store") or "")
        if country and store:
            outcomes[(country, store)] = payload
    return outcomes


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


def scrape_attempt_epoch(status: dict | None) -> int | None:
    if not status:
        return None
    outcome = str(status.get("outcome") or "")
    if outcome not in {"preserved", "refreshed"}:
        return None
    stamp = status.get("timestamp")
    if not stamp:
        return int(time.time())
    try:
        return int(
            datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .timestamp()
        )
    except ValueError:
        return int(time.time())


def annotation(level: str, path: str, message: str) -> None:
    safe_message = message.replace("\n", " ")
    print(f"::{level} file={path}::{safe_message}")


def _record(bucket: list[str], *, optional: bool, message: str) -> None:
    if optional:
        bucket.append(f"{message}; optional store, keeping last-good catalog")
    else:
        bucket.append(message)


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
    outcomes = scrape_outcomes()
    failures: list[str] = []
    summary = ["## Catalog monitoring", "", "| Catalog | Products | Age | Result |", "|---|---:|---:|---|"]

    for country, store, path in targets:
        relative = catalog_rel_path(country, store)
        cfg = store_config(country, store)
        optional = bool(cfg.get("optional"))
        count, read_error = catalog_count(path)
        minimum = int(cfg.get("minimum_products") or 0)
        baseline = baselines.get((country, store), 0)
        status = outcomes.get((country, store))
        attempt_at = scrape_attempt_epoch(status)
        changed_at = attempt_at or last_change_epoch(path)
        age_hours = (time.time() - changed_at) / 3600 if changed_at else float("inf")
        issues: list[str] = []
        warnings: list[str] = []

        if read_error:
            _record(issues if not optional else warnings, optional=optional, message=read_error)
        elif count == 0:
            _record(
                issues if not optional else warnings,
                optional=optional,
                message="catalog contains zero products",
            )
        elif count < minimum:
            _record(
                issues if not optional else warnings,
                optional=optional,
                message=f"{count} products is below configured minimum {minimum}",
            )

        if baseline > 0 and count < baseline * (1 - args.max_drop_ratio):
            drop_message = (
                f"count dropped from baseline {baseline} to {count} "
                f"(limit {args.max_drop_ratio:.0%})"
            )
            _record(
                issues if not optional else warnings,
                optional=optional,
                message=drop_message,
            )
        if baseline > 0 and count > baseline * args.max_growth_ratio:
            growth_message = (
                f"count grew from baseline {baseline} to {count} "
                f"(limit {args.max_growth_ratio:g}x)"
            )
            _record(
                issues if not optional else warnings,
                optional=optional,
                message=growth_message,
            )
        if age_hours > args.max_age_hours:
            age_message = (
                f"catalog has not changed for {age_hours:.1f}h "
                f"(limit {args.max_age_hours:g}h)"
            )
            # Optional stores and successful last-good retention in this run should
            # not block publishing fresher catalogs from other stores.
            if optional or attempt_at is not None:
                warnings.append(f"{age_message}; refresh attempted, keeping last-good catalog")
            else:
                issues.append(age_message)

        result = "OK" if not issues and not warnings else "; ".join([*issues, *warnings])
        summary.append(f"| `{country}/{store}` | {count} | {age_hours:.1f}h | {result} |")
        for issue in issues:
            message = f"{country}/{store}: {issue}. Check the store scraper logs and rerun this workflow."
            annotation("error", relative, message)
            failures.append(message)
        for warning in warnings:
            annotation(
                "warning",
                relative,
                f"{country}/{store}: {warning}. Check the store scraper logs when convenient.",
            )

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
