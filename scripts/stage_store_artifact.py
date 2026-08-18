#!/usr/bin/env python3
"""Stage one canonical store catalog and scrape status for Actions artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import catalog_rel_path, store_config, store_dir  # noqa: E402

MAX_RAW_FILE_BYTES = 50 * 1024 * 1024
MAX_RAW_TOTAL_BYTES = 200 * 1024 * 1024


def _stage_raw(
    country: str,
    store: str,
    output: Path,
    *,
    scrape_status: dict | None = None,
) -> int:
    cfg = store_config(country, store)
    workdir = store_dir(country, store)
    staged: list[dict] = []
    total = 0
    seen: set[Path] = set()
    for pattern in cfg.get("intermediate_globs") or []:
        for source in sorted(workdir.glob(pattern)):
            if not source.is_file() or source.resolve() in seen:
                continue
            seen.add(source.resolve())
            size = source.stat().st_size
            if size > MAX_RAW_FILE_BYTES or total + size > MAX_RAW_TOTAL_BYTES:
                print(f"::warning::Skipping oversized raw observation {source}")
                continue
            relative = source.relative_to(workdir)
            destination = output / country / store / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            staged.append(
                {
                    "path": str(relative),
                    "bytes": size,
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            )
            total += size
    if staged:
        manifest = output / country / store / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "country": country,
                    "store": store,
                    "capturedAt": datetime.now(timezone.utc).isoformat(),
                    "scrapeStatus": scrape_status or {},
                    "files": staged,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return len(staged)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "catalog")
    parser.add_argument("--raw-output", type=Path, default=ROOT / "artifacts" / "raw")
    parser.add_argument("--status-file", type=Path, required=True)
    args = parser.parse_args()

    relative = Path(catalog_rel_path(args.country, args.store))
    source = ROOT / relative
    if not source.is_file():
        print(f"::error file={relative}::Canonical catalog is missing and cannot be staged")
        return 1

    destination = args.output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

    if not args.status_file.is_file():
        args.status_file.parent.mkdir(parents=True, exist_ok=True)
        args.status_file.write_text(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "country": args.country,
                    "store": args.store,
                    "outcome": "unexpected_failure",
                    "reason": "scraper ended before writing a status file",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    try:
        scrape_status = json.loads(args.status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        scrape_status = {}
    raw_count = _stage_raw(
        args.country,
        args.store,
        args.raw_output,
        scrape_status=scrape_status,
    )
    print(f"Staged {relative}, {args.status_file}, and {raw_count} raw observation file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
