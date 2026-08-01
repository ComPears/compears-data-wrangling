#!/usr/bin/env python3
"""Stage one canonical store catalog and scrape status for Actions artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import catalog_rel_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "catalog")
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

    print(f"Staged {relative} and {args.status_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
