#!/usr/bin/env python3
"""Run a store scrape pipeline from config/stores.json.

Refuses to keep a below-minimum catalog overwrite: if the new catalog is too
small, restore the pre-scrape snapshot so CI bot-walls cannot wipe last-good data.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
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


ROOT = _bootstrap()
from config.paths import load_stores_config, store_config, store_dir  # noqa: E402


def _count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return len(data) if isinstance(data, list) else 0


def _snapshot_paths(workdir: Path, cfg: dict) -> list[Path]:
    paths = [workdir / cfg["catalog"]]
    for pattern in cfg.get("intermediate_globs") or []:
        paths.extend(sorted(workdir.glob(pattern)))
    # de-dupe while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _restore(backups: dict[Path, Path]) -> None:
    for path, backup in backups.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, path)


def _write_status(path: Path | None, **status: object) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **status,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run store scrape pipeline")
    parser.add_argument("--country", default=load_stores_config().get("default_country", "nl"))
    parser.add_argument("--store", required=True, help="Store slug, e.g. albert-heijn")
    parser.add_argument(
        "--soft-fail",
        action="store_true",
        help="Preserve last-good data and report a warning for scrape-source failures",
    )
    parser.add_argument("--status-file", type=Path, default=None)
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

    catalog = workdir / cfg["catalog"]
    minimum = int(cfg.get("minimum_products") or 0)
    optional = bool(cfg.get("optional"))
    tracked = _snapshot_paths(workdir, cfg)

    backup_root = Path(tempfile.mkdtemp(prefix=f"compear-{args.store}-"))
    backups: dict[Path, Path] = {}
    try:
        for path in tracked:
            if not path.is_file():
                continue
            rel = path.relative_to(workdir)
            dest = backup_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            backups[path] = dest

        before = _count(catalog)
        print(f"Pre-scrape catalog count: {before} (minimum {minimum})")

        for step in steps:
            print(f"=== {args.country}/{args.store}: {step} ===")
            result = subprocess.run(
                [sys.executable, step],
                cwd=workdir,
                check=False,
            )
            if result.returncode != 0:
                print(f"Pipeline failed at {step} (exit {result.returncode})", file=sys.stderr)
                # Restore last-good so a mid-pipeline crash cannot leave empty files.
                generated = _count(catalog)
                _restore(backups)
                restored = _count(catalog)
                _write_status(
                    args.status_file,
                    country=args.country,
                    store=args.store,
                    outcome="preserved",
                    reason=f"pipeline step {step} exited {result.returncode}",
                    before=before,
                    generated=generated,
                    final=restored,
                    minimum=minimum,
                )
                if args.soft_fail or optional:
                    print(f"::warning::{args.country}/{args.store} scrape failed; preserved {restored} last-good products")
                    return
                sys.exit(result.returncode)

        after = _count(catalog)
        print(f"Post-scrape catalog count: {after}")

        if minimum > 0 and after < minimum:
            print(
                f"⚠️ {args.country}/{args.store}: {after} products < minimum {minimum}; "
                "restoring last-good catalog and failing the scrape.",
                file=sys.stderr,
            )
            _restore(backups)
            restored = _count(catalog)
            print(f"Restored catalog count: {restored}")
            _write_status(
                args.status_file,
                country=args.country,
                store=args.store,
                outcome="preserved",
                reason=f"generated catalog below minimum ({after} < {minimum})",
                before=before,
                generated=after,
                final=restored,
                minimum=minimum,
            )
            # Optional stores should not fail the whole matrix when bot-walled.
            if args.soft_fail or optional:
                print(f"::warning::{args.country}/{args.store} returned {after} products; preserved {restored} last-good products")
                return
            sys.exit(1)

        print(f"✅ Pipeline complete → {catalog}")
        _write_status(
            args.status_file,
            country=args.country,
            store=args.store,
            outcome="refreshed",
            reason=None,
            before=before,
            generated=after,
            final=after,
            minimum=minimum,
        )
    finally:
        shutil.rmtree(backup_root, ignore_errors=True)


if __name__ == "__main__":
    main()
