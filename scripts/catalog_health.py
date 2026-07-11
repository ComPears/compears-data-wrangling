#!/usr/bin/env python3
"""Generate CI-friendly health and barcode coverage metrics for each catalog."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from barcode_utils import normalize_barcode
from config.paths import all_catalog_paths, catalog_rel_path, store_config
from product_sanitize import should_reject_name

DEFAULTS = {
    "stale_after_hours": 48,
    "warn_invalid_price_rate": 0.01,
    "max_invalid_price_rate": 0.10,
    "max_suspicious_price_rate": 0.02,
    "max_duplicate_identity_rate": 0.01,
    "max_duplicate_barcode_rate": 0.005,
    "minimum_barcode_coverage": 0.0,
}
# Per-store barcode coverage floors. Keep at 0 until scrapers populate `b` on catalog rows.
BARCODE_FLOORS: dict[str, float] = {}
SUSPICIOUS_PRICE_MIN = 0.05
SUSPICIOUS_PRICE_MAX = 500.0


def _rate(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _parse_price(value: Any) -> float | None:
    try:
        price = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def _scraped_at(entry: dict[str, Any]) -> datetime | None:
    value = entry.get("scrapedAt") or entry.get("scraped_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def analyze_catalog(
    country: str,
    slug: str,
    catalog: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    thresholds = {
        **DEFAULTS,
        "minimum_products": int(store_config(country, slug).get("minimum_products") or 0),
        "minimum_barcode_coverage": BARCODE_FLOORS.get(slug, 0.0),
    }
    result: dict[str, Any] = {
        "country": country,
        "store": slug,
        "catalog": catalog_rel_path(country, slug),
        "status": "error",
        "thresholds": thresholds,
        "issues": [],
        "metrics": {},
    }
    if not catalog.exists():
        result["issues"].append({"severity": "error", "code": "catalog_missing"})
        return result

    try:
        data = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        result["issues"].append(
            {"severity": "error", "code": "catalog_unreadable", "detail": str(error)}
        )
        return result
    if not isinstance(data, list):
        result["issues"].append({"severity": "error", "code": "catalog_not_array"})
        return result

    total = len(data)
    identities: Counter[str] = Counter()
    barcodes: Counter[str] = Counter()
    barcode_identities: dict[str, set[str]] = defaultdict(set)
    with_barcode = invalid_barcode = invalid_price = suspicious_price = 0
    missing_scraped_at = stale_scrape = malformed_rows = promo_in_name = 0
    newest_scrape: datetime | None = None

    for row in data:
        if not isinstance(row, dict):
            malformed_rows += 1
            continue
        identity = str(row.get("ik") or "").strip()
        if identity:
            identities[identity] += 1
        raw_barcode = row.get("b")
        if raw_barcode not in (None, ""):
            barcode = normalize_barcode(raw_barcode)
            if barcode:
                with_barcode += 1
                barcodes[barcode] += 1
                if identity:
                    barcode_identities[barcode].add(identity)
            else:
                invalid_barcode += 1
        price = _parse_price(row.get("p"))
        if price is None:
            invalid_price += 1
        elif price < SUSPICIOUS_PRICE_MIN or price > SUSPICIOUS_PRICE_MAX:
            suspicious_price += 1
        if should_reject_name(str(row.get("n") or "")):
            promo_in_name += 1
        scraped = _scraped_at(row)
        if scraped is None:
            missing_scraped_at += 1
        else:
            newest_scrape = max(newest_scrape, scraped) if newest_scrape else scraped
            if (now - scraped).total_seconds() > thresholds["stale_after_hours"] * 3600:
                stale_scrape += 1

    duplicate_identity = sum(count - 1 for count in identities.values() if count > 1)
    duplicate_barcode = sum(count - 1 for count in barcodes.values() if count > 1)
    conflicting_barcode = sum(1 for values in barcode_identities.values() if len(values) > 1)
    coverage = _rate(with_barcode, total)
    metrics = {
        "product_count": total,
        "barcode": {
            "valid_count": with_barcode,
            "coverage": coverage,
            "invalid_count": invalid_barcode,
            "duplicate_rows": duplicate_barcode,
            "conflicting_identities": conflicting_barcode,
        },
        "identity": {
            "present_count": sum(identities.values()),
            "duplicate_rows": duplicate_identity,
        },
        "price": {
            "invalid_count": invalid_price,
            "invalid_rate": _rate(invalid_price, total),
            "suspicious_count": suspicious_price,
            "suspicious_rate": _rate(suspicious_price, total),
            "suspicious_range": [SUSPICIOUS_PRICE_MIN, SUSPICIOUS_PRICE_MAX],
        },
        "scrape": {
            "missing_timestamp_count": missing_scraped_at,
            "stale_count": stale_scrape,
            "newest_at": newest_scrape.isoformat() if newest_scrape else None,
        },
        "malformed_rows": malformed_rows,
        "promo_in_name": promo_in_name,
    }
    result["metrics"] = metrics

    def issue(severity: str, code: str, actual: Any, threshold: Any) -> None:
        result["issues"].append(
            {"severity": severity, "code": code, "actual": actual, "threshold": threshold}
        )

    if total < thresholds["minimum_products"]:
        issue("error", "product_count_below_minimum", total, thresholds["minimum_products"])
    if metrics["price"]["invalid_rate"] > thresholds["max_invalid_price_rate"]:
        issue("error", "invalid_price_rate_high", metrics["price"]["invalid_rate"], thresholds["max_invalid_price_rate"])
    elif metrics["price"]["invalid_rate"] > thresholds["warn_invalid_price_rate"]:
        issue("warning", "invalid_price_rate_elevated", metrics["price"]["invalid_rate"], thresholds["warn_invalid_price_rate"])
    if metrics["price"]["suspicious_rate"] > thresholds["max_suspicious_price_rate"]:
        issue("warning", "suspicious_price_rate_high", metrics["price"]["suspicious_rate"], thresholds["max_suspicious_price_rate"])
    if _rate(duplicate_identity, total) > thresholds["max_duplicate_identity_rate"]:
        issue("error", "duplicate_identity_rate_high", _rate(duplicate_identity, total), thresholds["max_duplicate_identity_rate"])
    if _rate(duplicate_barcode, total) > thresholds["max_duplicate_barcode_rate"]:
        issue("warning", "duplicate_barcode_rate_high", _rate(duplicate_barcode, total), thresholds["max_duplicate_barcode_rate"])
    if conflicting_barcode:
        issue("warning", "barcode_identity_conflicts", conflicting_barcode, 0)
    if coverage < thresholds["minimum_barcode_coverage"]:
        issue("error", "barcode_coverage_below_minimum", coverage, thresholds["minimum_barcode_coverage"])
    if invalid_barcode:
        issue("warning", "invalid_barcodes", invalid_barcode, 0)
    if missing_scraped_at:
        issue("warning", "missing_scrape_timestamps", missing_scraped_at, 0)
    if stale_scrape:
        issue("error", "stale_scrape_rows", stale_scrape, 0)
    if malformed_rows or promo_in_name:
        issue("warning", "malformed_or_rejected_rows", malformed_rows + promo_in_name, 0)

    severities = {item["severity"] for item in result["issues"]}
    result["status"] = "error" if "error" in severities else "warning" if severities else "pass"
    return result


def build_report(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    stores = [
        analyze_catalog(country, slug, path, now=now)
        for country, slug, path in all_catalog_paths()
    ]
    statuses = Counter(store["status"] for store in stores)
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "status": "error" if statuses["error"] else "warning" if statuses["warning"] else "pass",
        "summary": {
            "stores": len(stores),
            "pass": statuses["pass"],
            "warning": statuses["warning"],
            "error": statuses["error"],
            "products": sum(store["metrics"].get("product_count", 0) for store in stores),
            "barcodes": sum(store["metrics"].get("barcode", {}).get("valid_count", 0) for store in stores),
        },
        "stores": stores,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "catalog-health.json")
    parser.add_argument("--fail-on", choices=("error", "warning", "never"), default="error")
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Store            Products  Barcode coverage  Invalid price  Status")
    for store in report["stores"]:
        metrics = store["metrics"]
        print(
            f"{store['store']:<16} {metrics.get('product_count', 0):>8}  "
            f"{metrics.get('barcode', {}).get('coverage', 0):>15.1%}  "
            f"{metrics.get('price', {}).get('invalid_rate', 0):>13.1%}  {store['status']}"
        )
    print(f"Overall: {report['status']}; artifact: {args.output}")
    if args.fail_on == "warning" and report["status"] in {"warning", "error"}:
        return 1
    if args.fail_on == "error" and report["status"] == "error":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
