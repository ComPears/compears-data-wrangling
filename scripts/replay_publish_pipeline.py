#!/usr/bin/env python3
"""Replay GitHub's publish job against downloaded catalog artifacts.

Run this in a disposable worktree: artifact contents intentionally overwrite
catalogs and scrape-status files, exactly as actions/download-artifact does.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, catalog_rel_path


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]
    env: dict[str, str] | None = None


def copy_catalog_artifacts(artifact_root: Path, workspace: Path) -> int:
    copied = 0
    missing: list[str] = []
    for country, store, _catalog in all_catalog_paths():
        artifact = artifact_root / f"catalog-{country}-{store}"
        if not artifact.is_dir():
            missing.append(artifact.name)
            continue
        source_catalog = artifact / catalog_rel_path(country, store)
        source_status = artifact / "reports" / "scrape-status" / f"{country}-{store}.json"
        if not source_catalog.is_file() or not source_status.is_file():
            missing.append(f"{artifact.name} (catalog/status incomplete)")
            continue
        shutil.copytree(artifact, workspace, dirs_exist_ok=True)
        copied += 1
    if missing:
        raise RuntimeError("Missing scraper artifacts: " + ", ".join(missing))
    return copied


def publish_steps() -> tuple[Step, ...]:
    python = sys.executable
    return (
        Step("Summarize store refresh outcomes", (python, "scripts/summarize_scrape_status.py")),
        Step("Sanitize canonical product JSON", (python, "scripts/sanitize_all_stores.py")),
        Step("Validate required store output counts", (python, "scripts/validate_store_output.py")),
        Step(
            "Run catalog regression tests",
            (python, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"),
        ),
        Step("Validate data quality report", (python, "scripts/validate_products.py")),
        Step(
            "Generate catalog health report",
            (python, "scripts/catalog_health.py", "--fail-on", "error"),
        ),
        Step("Build confidence-scored comparison index", (python, "scripts/build_match_index.py")),
        Step(
            "Catalog freshness and drop alerts",
            (python, "scripts/workflow_catalog_alerts.py"),
            {
                "CATALOG_MAX_AGE_HOURS": "48",
                "CATALOG_MAX_DROP_RATIO": "0.2",
                "CATALOG_MAX_GROWTH_RATIO": "1.75",
            },
        ),
        Step("Write publish manifest", (python, "scripts/write_catalog_manifest.py")),
        Step(
            "Remove stale intermediate JSON",
            (python, "scripts/prune_stale_artifacts.py", "--from-git"),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=ROOT)
    parser.add_argument(
        "--apply-artifacts",
        action="store_true",
        help="Acknowledge that catalogs in --workspace will be overwritten",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run later diagnostics after a failure instead of matching GitHub fail-fast behavior",
    )
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    artifact_root = args.artifact_root.resolve()
    if not args.apply_artifacts:
        parser.error("--apply-artifacts is required because replay overwrites catalog files")
    if not (workspace / "config" / "stores.json").is_file():
        parser.error(f"not a data-wrangling workspace: {workspace}")
    if not artifact_root.is_dir():
        parser.error(f"artifact root does not exist: {artifact_root}")

    copied = copy_catalog_artifacts(artifact_root, workspace)
    print(f"Replaying {copied} catalog artifacts in {workspace}", flush=True)

    failures: list[str] = []
    for index, step in enumerate(publish_steps(), start=1):
        print(f"\n[{index}/{len(publish_steps())}] {step.name}", flush=True)
        env = os.environ.copy()
        env.update(step.env or {})
        completed = subprocess.run(step.command, cwd=workspace, env=env, check=False)
        if completed.returncode:
            failures.append(f"{step.name} (exit {completed.returncode})")
            if not args.continue_on_error:
                break

    if failures:
        print("\nPublish replay failed: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("\nPublish replay passed every GitHub publish gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
