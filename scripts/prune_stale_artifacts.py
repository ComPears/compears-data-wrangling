#!/usr/bin/env python3
"""Remove intermediate scrape artifacts; keep only canonical per-store JSON."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, intermediate_globs

LEGACY_FILES = {
    ROOT / "supermarkets.json",
    ROOT / "final_aldi.json",
}


def collect_removable_paths() -> list[Path]:
    canonical = {catalog.resolve() for _c, _s, catalog in all_catalog_paths()}
    removable: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen or resolved in canonical:
            return
        seen.add(resolved)
        removable.append(path)

    for legacy in LEGACY_FILES:
        if legacy.exists():
            add(legacy)

    for pattern in intermediate_globs():
        for match in ROOT.glob(pattern):
            if match.is_file():
                add(match)

    return sorted(removable)


def prune_from_git(paths: list[Path]) -> list[Path]:
    removed: list[Path] = []
    for path in paths:
        rel = path.relative_to(ROOT)
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(rel)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if path.exists():
                path.unlink()
                removed.append(path)
            continue
        subprocess.run(["git", "rm", "-f", str(rel)], cwd=ROOT, check=True)
        removed.append(path)
    return removed


def prune_local(paths: list[Path]) -> list[Path]:
    removed: list[Path] = []
    for path in paths:
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune stale scrape artifacts")
    parser.add_argument(
        "--from-git",
        action="store_true",
        help="Remove tracked files via git rm (for CI)",
    )
    args = parser.parse_args()

    paths = collect_removable_paths()
    if not paths:
        print("Nothing to prune.")
        return

    removed = prune_from_git(paths) if args.from_git else prune_local(paths)
    print(f"Pruned {len(removed)} stale artifact(s).")


if __name__ == "__main__":
    main()
