#!/usr/bin/env python3
"""Write a versioned catalog publish manifest for sync/observability."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, catalog_rel_path, store_config
from data_contract import utc_iso


def _count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return len(data) if isinstance(data, list) else 0


def _latest_observation(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    stamps = [
        utc_iso(row.get("observedAt") or row.get("scrapedAt") or row.get("scraped_at"))
        for row in rows
        if isinstance(row, dict)
    ] if isinstance(rows, list) else []
    return max(stamp for stamp in stamps if stamp) if any(stamps) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "catalog-manifest.json",
    )
    parser.add_argument(
        "--status-dir",
        type=Path,
        default=ROOT / "reports" / "scrape-status",
    )
    parser.add_argument("--sha", default=os.getenv("GITHUB_SHA") or "")
    args = parser.parse_args()

    statuses: dict[tuple[str, str], dict] = {}
    if args.status_dir.is_dir():
        for path in args.status_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            country = str(payload.get("country") or "")
            store = str(payload.get("store") or "")
            if country and store:
                statuses[(country, store)] = payload

    generated_at = datetime.now(timezone.utc)
    stores: list[dict] = []
    outcomes = Counter()
    for country, store, catalog in all_catalog_paths():
        cfg = store_config(country, store)
        status = statuses.get((country, store), {})
        outcome = str(status.get("outcome") or "unchanged")
        outcomes[outcome] += 1
        count = _count(catalog)
        attempted_at = utc_iso(status.get("attempted_at") or status.get("timestamp"))
        last_successful_at = utc_iso(status.get("last_successful_at")) or _latest_observation(catalog)
        freshness_hours = None
        if last_successful_at:
            observed = datetime.fromisoformat(last_successful_at)
            freshness_hours = round((generated_at - observed).total_seconds() / 3600, 2)
        stores.append(
            {
                "country": country,
                "store": store,
                "catalog": catalog_rel_path(country, store),
                "optional": bool(cfg.get("optional")),
                "minimum_products": int(cfg.get("minimum_products") or 0),
                "products": count,
                "outcome": outcome,
                "reason": status.get("reason"),
                "attempted_at": attempted_at,
                "last_successful_at": last_successful_at,
                "freshness_hours": freshness_hours,
            }
        )

    required = [row for row in stores if not row["optional"]]
    required_ok = sum(
        1
        for row in required
        if row["products"] >= int(row["minimum_products"] or 0)
        and row["products"] > 0
        and row["last_successful_at"]
        and row["freshness_hours"] is not None
        and float(row["freshness_hours"]) >= -1
        and float(row["freshness_hours"]) <= 48
    )

    manifest = {
        "schema_version": 2,
        "generated_at": generated_at.isoformat(),
        "source_sha": args.sha,
        "summary": {
            "stores": len(stores),
            "required_stores": len(required),
            "required_ok": required_ok,
            "outcomes": dict(outcomes),
            "products": sum(int(row["products"]) for row in stores),
        },
        "stores": stores,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    summary = [
        "## Catalog publish manifest",
        "",
        f"- Required catalogs OK: **{required_ok}/{len(required)}**",
        f"- Outcomes: `{dict(outcomes)}`",
        f"- Total products: **{manifest['summary']['products']}**",
        f"- Manifest: `{args.output}`",
        "",
    ]
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(summary) + "\n")

    print(json.dumps(manifest["summary"], indent=2))
    if required_ok != len(required):
        print(
            f"::error::Only {required_ok}/{len(required)} required catalogs are fresh and usable; "
            "refusing to publish"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
