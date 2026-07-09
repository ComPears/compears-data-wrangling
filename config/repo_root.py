"""Locate compears-data-wrangling repository root."""

from __future__ import annotations

from pathlib import Path

MARKER = Path("config") / "stores.json"


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / MARKER).is_file():
            return candidate
    raise RuntimeError(f"Could not find repo root (missing {MARKER}) from {current}")


def bootstrap_sys_path(start: Path | None = None) -> Path:
    import sys

    root = find_repo_root(start)
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root
