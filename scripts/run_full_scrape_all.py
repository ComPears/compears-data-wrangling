#!/usr/bin/env python3
"""Run full scrape pipelines for NL + UK + DE with bounded parallelism."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / ".local-scrape-logs"
PYTHON = ROOT / "venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

STORES = [
    ("nl", "albert-heijn"),
    ("nl", "jumbo"),
    ("nl", "aldi"),
    ("nl", "dirk"),
    ("nl", "lidl"),
    ("nl", "coop"),
    ("nl", "plus"),
    ("uk", "tesco"),
    ("uk", "sainsburys"),
    ("uk", "asda"),
    ("uk", "morrisons"),
    ("uk", "aldi-uk"),
    ("uk", "lidl-uk"),
    ("de", "edeka"),
    ("de", "rewe"),
    ("de", "lidl-de"),
    ("de", "aldi-sud"),
    ("de", "penny"),
]


def run_one(country: str, store: str, soft_fail: bool) -> dict:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOG_DIR / f"{country}_{store}_{stamp}.log"
    cmd = [
        str(PYTHON),
        str(ROOT / "scripts" / "run_store_pipeline.py"),
        "--country",
        country,
        "--store",
        store,
    ]
    if soft_fail:
        cmd.append("--soft-fail")

    env = os.environ.copy()
    env.setdefault("UK_MAX_QUERIES", "80")
    env.setdefault("DE_MAX_QUERIES", "80")
    env.setdefault("UK_MAX_BLOCKED_QUERIES", "3")
    env.setdefault("DE_MAX_BLOCKED_QUERIES", "3")
    env.setdefault("UK_MAX_EMPTY_QUERIES", "5")
    env.setdefault("DE_MAX_EMPTY_QUERIES", "5")
    # Prefer system Chrome for Asda when available; otherwise Chromium.
    if store == "asda" and "PLAYWRIGHT_CHANNEL" not in env:
        env["PLAYWRIGHT_CHANNEL"] = "chromium"

    started = time.time()
    env.setdefault("PYTHONUNBUFFERED", "1")
    print(f"[start] {country}/{store} → {log_path.name}", flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {' '.join(cmd)}\n")
        log.flush()
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    duration = time.time() - started
    status = "ok" if proc.returncode == 0 else f"exit={proc.returncode}"
    print(f"[done]  {country}/{store} {status} in {duration/60:.1f}m", flush=True)
    return {
        "country": country,
        "store": store,
        "returncode": proc.returncode,
        "duration_s": round(duration, 1),
        "log": str(log_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-parallel", type=int, default=5)
    parser.add_argument("--soft-fail", action="store_true", default=True)
    parser.add_argument("--no-soft-fail", action="store_true")
    parser.add_argument(
        "--only",
        nargs="*",
        help="Optional country/store filters like nl/plus uk/tesco",
    )
    args = parser.parse_args()
    soft = not args.no_soft_fail
    jobs = STORES
    if args.only:
        wanted = set(args.only)
        jobs = [j for j in STORES if f"{j[0]}/{j[1]}" in wanted]
        if not jobs:
            print("No matching stores for --only", file=sys.stderr)
            return 2

    summary_path = LOG_DIR / f"summary_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    results = []
    print(
        f"Running {len(jobs)} store pipelines (max_parallel={args.max_parallel}, soft_fail={soft})",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=max(1, args.max_parallel)) as pool:
        futures = {
            pool.submit(run_one, country, store, soft): (country, store)
            for country, store in jobs
        }
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda r: (r["country"], r["store"]))
    ok = sum(1 for r in results if r["returncode"] == 0)
    fail = len(results) - ok
    import json

    payload = {"ok": ok, "fail": fail, "results": results}
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    print(f"Summary written to {summary_path}", flush=True)
    # Soft-fail scrapes still return 0 from pipeline when optional; treat hard failures only
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
