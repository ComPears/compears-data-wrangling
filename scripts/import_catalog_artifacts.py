#!/usr/bin/env python3
"""Import only configured catalog/status JSON, never executable artifact content."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, catalog_rel_path

MAX_FILE_BYTES = 50 * 1024 * 1024


def _contained_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Artifact path must be relative and contained")
    candidate = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink is not allowed: {relative}")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes root: {relative}")
    return candidate


def copy_catalog_artifacts(artifact_root: Path, workspace: Path) -> int:
    """Validate the complete batch before overwriting any allowlisted data files."""
    artifact_root = artifact_root.resolve()
    workspace = workspace.resolve()
    planned: list[tuple[Path, bytes]] = []
    stores = all_catalog_paths()
    for country, store, _ in stores:
        artifact_name = Path(f"catalog-{country}-{store}")
        artifact = _contained_path(artifact_root, artifact_name)
        if not artifact.is_dir():
            raise ValueError(f"Missing scraper artifact: {artifact_name}")
        catalog = Path(catalog_rel_path(country, store))
        status = Path("reports/scrape-status") / f"{country}-{store}.json"
        allowed = {catalog, status}
        for entry in artifact.rglob("*"):
            relative = entry.relative_to(artifact)
            if entry.is_symlink() or (not entry.is_dir() and relative not in allowed):
                raise ValueError(f"Unexpected artifact entry: {artifact_name / relative}")
        for relative, expected_type in ((catalog, list), (status, dict)):
            source = _contained_path(artifact, relative)
            destination = _contained_path(workspace, relative)
            if not source.is_file():
                raise ValueError(f"Missing artifact file: {artifact_name / relative}")
            if source.stat().st_size > MAX_FILE_BYTES:
                raise ValueError(f"Oversized artifact file: {artifact_name / relative}")
            payload = source.read_bytes()
            value = json.loads(payload)
            if not isinstance(value, expected_type):
                raise ValueError(f"Invalid JSON shape: {artifact_name / relative}")
            planned.append((destination, payload))
    for destination, payload in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    return len(stores)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=ROOT)
    args = parser.parse_args()
    count = copy_catalog_artifacts(args.artifact_root, args.workspace)
    print(f"Imported {count} validated catalog/status artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
