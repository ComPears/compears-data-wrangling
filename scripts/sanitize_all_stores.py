#!/usr/bin/env python3
"""Sanitize all canonical store JSON files in-place."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, catalog_rel_path, country_config
from product_sanitize import dedupe_by_identity, sanitize_entry_with_reason

STATUS_DIR = ROOT / "reports" / "scrape-status"
QUARANTINE_DIR = ROOT / "reports" / "quarantine"


def _dedupe_coop_against_plus() -> None:
    import importlib.util

    module_path = ROOT / "scripts" / "dedupe_coop_against_plus.py"
    spec = importlib.util.spec_from_file_location("dedupe_coop_against_plus", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load dedupe module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.dedupe_coop_against_plus()


def _statuses() -> dict[tuple[str, str], dict]:
    statuses: dict[tuple[str, str], dict] = {}
    if not STATUS_DIR.is_dir():
        return statuses
    for path in STATUS_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        key = (str(payload.get("country") or ""), str(payload.get("store") or ""))
        if all(key):
            statuses[key] = payload
    return statuses


def sanitize_file(
    country: str,
    store: str,
    rel_path: str,
    *,
    observed_at: str | None = None,
) -> dict[str, int]:
    path = ROOT / rel_path
    stats = {
        "input": 0,
        "kept": 0,
        "rejected": 0,
        "deduped": 0,
    }
    if not path.exists():
        print(f"skip missing {rel_path}")
        return stats

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"skip non-array {rel_path}")
        return stats

    stats["input"] = len(data)
    kept: list[dict] = []
    rejected: list[dict] = []
    currency = str(country_config(country).get("currency") or "")

    for entry in data:
        if not isinstance(entry, dict):
            rejected.append({"reason": "malformed_row", "row": entry})
            stats["rejected"] += 1
            continue
        cleaned, reason = sanitize_entry_with_reason(
            entry,
            country=country,
            store=store,
            currency=currency,
            observed_at=observed_at,
        )
        if cleaned is None:
            rejected.append({"reason": reason or "unknown", "row": entry})
            stats["rejected"] += 1
        else:
            kept.append(cleaned)

    deduped, removed = dedupe_by_identity(kept)
    stats["deduped"] = removed
    stats["kept"] = len(deduped)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)

    reject_path = QUARANTINE_DIR / f"{country}-{store}.json"
    if rejected:
        reject_path.parent.mkdir(parents=True, exist_ok=True)
        with open(reject_path, "w", encoding="utf-8") as f:
            json.dump(rejected, f, indent=2, ensure_ascii=False)
    elif reject_path.exists():
        reject_path.unlink()

    print(
        f"✅ {rel_path}: {stats['input']} in → {stats['kept']} kept, "
        f"{stats['rejected']} rejected, {stats['deduped']} dupes"
    )
    return stats


def main() -> None:
    totals = {"input": 0, "kept": 0, "rejected": 0, "deduped": 0}
    statuses = _statuses()
    for country, slug, catalog in all_catalog_paths():
        rel = catalog_rel_path(country, slug)
        status = statuses.get((country, slug), {})
        outcome = str(status.get("outcome") or "")
        observed_at = status.get("last_successful_at")
        if not observed_at and outcome == "refreshed":
            observed_at = status.get("attempted_at") or status.get("timestamp")
        stats = sanitize_file(country, slug, rel, observed_at=observed_at)
        for key in totals:
            totals[key] += stats[key]
    print(
        f"TOTAL: {totals['input']} → {totals['kept']} kept, "
        f"{totals['rejected']} rejected, {totals['deduped']} dupes"
    )
    _dedupe_coop_against_plus()


if __name__ == "__main__":
    main()
