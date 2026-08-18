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


def baseline_counts() -> dict[tuple[str, str], dict[str, int]]:
    """Read the last published catalogs from git, not the report just generated."""
    git_counts: dict[tuple[str, str], dict[str, int]] = {}
    for country, store, _path in all_catalog_paths():
        relative = catalog_rel_path(country, store)
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        try:
            rows = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
        if not isinstance(rows, list):
            continue
        versions = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                versions.append(int(row.get("schemaVersion") or 1))
            except (TypeError, ValueError):
                versions.append(1)
        git_counts[(country, store)] = {
            "count": len(rows),
            "schema_version": min(versions, default=1),
        }
    if git_counts:
        return git_counts

    # Non-git/test fallback for older report fixtures.
    if not BASELINE_PATH.exists():
        return {}
    with open(BASELINE_PATH, encoding="utf-8") as handle:
        rows = json.load(handle)
    return {
        (str(row.get("country") or "nl"), str(row["store"])): {
            "count": int(row.get("total") or 0),
            "schema_version": int(row.get("schema_version") or 1),
        }
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


def last_successful_epoch(status: dict | None) -> int | None:
    if not status:
        return None
    outcome = str(status.get("outcome") or "")
    if outcome not in {"preserved", "refreshed"}:
        return None
    stamp = status.get("last_successful_at")
    if not stamp and outcome == "refreshed":
        stamp = status.get("attempted_at") or status.get("timestamp")
    if not stamp:
        return None
    try:
        return int(
            datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .timestamp()
        )
    except ValueError:
        return None


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
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Emit alerts as warnings and always exit 0 (publish must not be blocked)",
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
        baseline_info = baselines.get((country, store), {})
        baseline = int(baseline_info.get("count") or 0)
        baseline_schema = int(baseline_info.get("schema_version") or 1)
        status = outcomes.get((country, store))
        successful_at = last_successful_epoch(status)
        # If an attempt wrote a status, only a real successful observation can
        # establish freshness. Sanitizer changes to a preserved catalog are not
        # evidence that the retailer was observed again.
        changed_at = successful_at if status else last_change_epoch(path)
        changed_at = changed_at or 0
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

        if baseline > 0 and baseline_schema >= 2 and count < baseline * (1 - args.max_drop_ratio):
            drop_message = (
                f"count dropped from baseline {baseline} to {count} "
                f"(limit {args.max_drop_ratio:.0%})"
            )
            _record(
                issues if not optional else warnings,
                optional=optional,
                message=drop_message,
            )
        if baseline > 0 and baseline_schema >= 2 and count > baseline * args.max_growth_ratio:
            growth_message = (
                f"count grew from baseline {baseline} to {count} "
                f"(limit {args.max_growth_ratio:g}x)"
            )
            _record(
                issues if not optional else warnings,
                optional=optional,
                message=growth_message,
            )
        if baseline > 0 and baseline_schema < 2 and count != baseline:
            warnings.append(
                f"count comparison reset during schema v2 migration ({baseline} to {count})"
            )
        if age_hours > args.max_age_hours:
            age_message = (
                f"catalog has not changed for {age_hours:.1f}h "
                f"(limit {args.max_age_hours:g}h)"
            )
            # A failed attempt is not freshness. Optional stores remain warnings;
            # stale required stores block publication until genuinely refreshed.
            if optional:
                warnings.append(f"{age_message}; optional store, keeping last-good catalog")
            else:
                issues.append(age_message)
        if age_hours < -1:
            future_message = f"catalog observation time is {-age_hours:.1f}h in the future"
            if optional:
                warnings.append(f"{future_message}; optional store, keeping last-good catalog")
            else:
                issues.append(future_message)

        result = "OK" if not issues and not warnings else "; ".join([*issues, *warnings])
        summary.append(f"| `{country}/{store}` | {count} | {age_hours:.1f}h | {result} |")
        for issue in issues:
            message = (
                f"{country}/{store}: {issue}. "
                "Check the store scraper logs and rerun this workflow."
            )
            if args.warn_only:
                annotation("warning", relative, message)
            else:
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

    if args.warn_only:
        print(
            f"Catalog monitoring completed in warn-only mode for {len(targets)} catalog(s)."
        )
        return 0
    if failures:
        print(f"Catalog monitoring failed with {len(failures)} actionable alert(s).")
        return 1
    print(f"Catalog monitoring passed for {len(targets)} catalog(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
