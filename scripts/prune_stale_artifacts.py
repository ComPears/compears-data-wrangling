#!/usr/bin/env python3
"""Remove intermediate scrape artifacts; keep only canonical per-store JSON."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Consumed by compear-backend seed (seedService.ts STORE_CONFIG).
CANONICAL_FILES = {
    ROOT / "AH/structured_all_merged.json",
    ROOT / "ALDI/structured_aldi.json",
    ROOT / "DIRK/dirk_all.json",
    ROOT / "JUMBO/jumbo_structured.json",
    ROOT / "LIDL/lidl_structured.json",
    ROOT / "COOP/coop_structured.json",
    ROOT / "PLUS/structured_plus.json",
}

# Legacy / duplicate outputs — safe to delete from the repo.
LEGACY_FILES = {
    ROOT / "supermarkets.json",
    ROOT / "final_aldi.json",
}

# Intermediate paths produced during scrape → merge → structure.
INTERMEDIATE_GLOBS = [
    "AH/new_results/*.json",
    "AH/AH.json",
    "AH/ah_structured.json",
    "ALDI/aldi_results/*.json",
    "ALDI/merged_aldi.json",
    "JUMBO/JSONs/*.json",
    "JUMBO/Jumbo.json",
    "DIRK/JSONs/*.json",
    "PLUS/plus.json",
    "LIDL/lidl.json",
    "COOP/coop.json",
]


def collect_removable_paths() -> list[Path]:
    removable: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        if resolved in CANONICAL_FILES:
            return
        seen.add(resolved)
        removable.append(path)

    for legacy in LEGACY_FILES:
        if legacy.exists():
            add(legacy)

    for pattern in INTERMEDIATE_GLOBS:
        for match in ROOT.glob(pattern):
            if match.is_file():
                add(match)

    return sorted(removable)


def prune_from_git(paths: list[Path]) -> list[Path]:
    removed: list[Path] = []
    for path in paths:
        rel = path.relative_to(ROOT)
        tracked = (
            subprocess.run(
                ["git", "ls-files", "--error-unmatch", str(rel)],
                cwd=ROOT,
                capture_output=True,
            ).returncode
            == 0
        )
        if tracked:
            subprocess.run(["git", "rm", "-f", "--ignore-unmatch", str(rel)], cwd=ROOT, check=True)
            removed.append(path)
        elif path.exists():
            path.unlink()
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-git",
        action="store_true",
        help="Also untrack removed files with git rm (for CI commits).",
    )
    parser.add_argument("--dry-run", action="store_true", help="List paths only.")
    args = parser.parse_args()

    paths = collect_removable_paths()
    if args.dry_run:
        for path in paths:
            print(path.relative_to(ROOT))
        print(f"Would remove {len(paths)} file(s).")
        return

    removed = prune_from_git(paths) if args.from_git else prune_local(paths)
    for path in removed:
        print(f"removed {path.relative_to(ROOT)}")
    print(f"Pruned {len(removed)} stale artifact(s).")


if __name__ == "__main__":
    main()
