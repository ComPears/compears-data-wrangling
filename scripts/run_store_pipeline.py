#!/usr/bin/env python3
"""Run a store scrape pipeline from config/stores.json."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _bootstrap() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / "config" / "stores.json").is_file():
            root = str(candidate)
            if root not in sys.path:
                sys.path.insert(0, root)
            return candidate
    raise RuntimeError("Could not find compears-data-wrangling repo root")


_bootstrap()
from config.paths import load_stores_config, store_config, store_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run store scrape pipeline")
    parser.add_argument("--country", default=load_stores_config().get("default_country", "nl"))
    parser.add_argument("--store", required=True, help="Store slug, e.g. albert-heijn")
    args = parser.parse_args()

    cfg = store_config(args.country, args.store)
    workdir = store_dir(args.country, args.store)
    if not workdir.is_dir():
        print(f"Store directory not found: {workdir}", file=sys.stderr)
        sys.exit(1)

    steps = cfg.get("pipeline") or []
    if not steps:
        print(f"No pipeline configured for {args.country}/{args.store}", file=sys.stderr)
        sys.exit(1)

    for step in steps:
        print(f"=== {args.country}/{args.store}: {step} ===")
        result = subprocess.run(
            [sys.executable, step],
            cwd=workdir,
            check=False,
        )
        if result.returncode != 0:
            print(f"Pipeline failed at {step} (exit {result.returncode})", file=sys.stderr)
            sys.exit(result.returncode)

    catalog = workdir / cfg["catalog"]
    print(f"✅ Pipeline complete → {catalog}")


if __name__ == "__main__":
    main()
