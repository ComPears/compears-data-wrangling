#!/usr/bin/env python3
"""Render per-store scrape outcomes in the GitHub Actions summary."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path


def main() -> int:
    status_dir = Path("reports/scrape-status")
    rows: list[dict] = []
    for path in sorted(status_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"::warning file={path}::Could not read scrape status: {error}")
            continue
        rows.append(payload)

    outcomes = Counter(str(row.get("outcome") or "unknown") for row in rows)
    summary = [
        "## Supermarket refresh results",
        "",
        (
            f"Coverage: **{outcomes.get('refreshed', 0)} refreshed**, "
            f"**{outcomes.get('preserved', 0)} preserved**, "
            f"**{outcomes.get('unexpected_failure', 0) + outcomes.get('unknown', 0)} other** "
            f"({len(rows)} stores)"
        ),
        "",
        "| Store | Outcome | Products | Detail |",
        "|---|---|---:|---|",
    ]
    for row in rows:
        store = f"{row.get('country', '?')}/{row.get('store', '?')}"
        outcome = str(row.get("outcome") or "unknown")
        products = row.get("final", "—")
        reason = str(row.get("reason") or "Fresh catalog accepted").replace("|", "\\|")
        summary.append(f"| `{store}` | {outcome} | {products} | {reason} |")
        if outcome != "refreshed":
            print(f"::warning::{store}: {reason}; last-good catalog retained")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(summary) + "\n")
    print(f"Summarized {len(rows)} scraper outcome(s): {dict(outcomes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
