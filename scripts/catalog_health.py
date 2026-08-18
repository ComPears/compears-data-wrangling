#!/usr/bin/env python3
"""Generate CI-friendly health and barcode coverage metrics for each catalog."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from barcode_utils import normalize_barcode
from category_utils import CANONICAL_CATEGORIES
from config.paths import all_catalog_paths, catalog_rel_path, store_config
from data_contract import is_valid_quantity, is_valid_unit_price, valid_http_url
from product_sanitize import should_reject_name

DEFAULTS = {
    "stale_after_hours": 48,
    "warn_invalid_price_rate": 0.001,
    "max_invalid_price_rate": 0.005,
    "max_suspicious_price_rate": 0.02,
    "max_duplicate_identity_rate": 0.01,
    "max_duplicate_barcode_rate": 0.005,
    "minimum_barcode_coverage": 0.0,
    "minimum_quantity_coverage": 0.90,
    "target_quantity_coverage": 0.90,
    "minimum_unit_price_coverage": 0.85,
    "minimum_brand_coverage": 0.05,
    "minimum_category_coverage": 0.50,
    "minimum_product_url_coverage": 0.50,
    "minimum_image_url_coverage": 0.80,
}
# Soft floors after 2026-08-03 full scrape + AH GTIN-14 fix (~7.9% AH `b`).
# PLUS/Dirk enrichment still returns 0% in catalog `b` — keep those at 0 until
# PDP extractors land real rates. Jumbo catalog `b` stays sparse (seed mines DAM URLs).
BARCODE_FLOORS: dict[str, float] = {
    "albert-heijn": 0.01,
    "plus": 0.0,
    "dirk": 0.0,
    "jumbo": 0.0,
}
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
    value = entry.get("observedAt") or entry.get("scrapedAt") or entry.get("scraped_at")
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
    cfg = store_config(country, slug)
    thresholds = {
        **DEFAULTS,
        "minimum_products": int(cfg.get("minimum_products") or 0),
        "minimum_barcode_coverage": BARCODE_FLOORS.get(slug, 0.0),
    }
    for key in ("minimum_quantity_coverage", "target_quantity_coverage"):
        if cfg.get(key) is not None:
            thresholds[key] = float(cfg[key])
    if cfg.get("maximum_catalog_age_hours") is not None:
        thresholds["stale_after_hours"] = float(cfg["maximum_catalog_age_hours"])
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
    with_quantity = with_unit_price = with_brand = with_category = 0
    with_product_url = with_image_url = 0
    contract_errors = 0
    contract_error_reasons: Counter[str] = Counter()
    missing_scraped_at = stale_scrape = future_scrape = malformed_rows = promo_in_name = 0
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
        quantity = row.get("quantity")
        quantity_valid = is_valid_quantity(quantity)
        if quantity_valid:
            with_quantity += 1
        expected_currency = {"nl": "EUR", "de": "EUR", "uk": "GBP"}.get(country)
        unit_price_valid = bool(
            quantity_valid
            and expected_currency
            and is_valid_unit_price(
                row.get("unitPrice"),
                price=str(row.get("p") or ""),
                currency=expected_currency,
                quantity=quantity,
            )
        )
        if unit_price_valid:
            with_unit_price += 1
        brand_source = str(row.get("brandSource") or "").strip().lower()
        if str(row.get("bn") or "").strip() and brand_source in {
            "retailer",
            "gtin",
            "known_name",
        }:
            with_brand += 1
        category = str(row.get("c") or "")
        if category in CANONICAL_CATEGORIES and category != "Other":
            with_category += 1
        if valid_http_url(row.get("productUrl")):
            with_product_url += 1
        if valid_http_url(row.get("imageUrl")):
            with_image_url += 1
        row_contract_errors = {
            "schema_version": row.get("schemaVersion") != 2,
            "country": row.get("country") != country,
            "retailer": row.get("retailer") != slug,
            "currency": bool(expected_currency and row.get("currency") != expected_currency),
            "price_type": row.get("priceType") not in {"regular", "promotion", "loyalty"},
            "category": category not in CANONICAL_CATEGORIES,
            "quantity_shape": isinstance(quantity, dict) and not quantity_valid,
            "unit_price": quantity_valid and not unit_price_valid,
            "product_url": bool(
                row.get("productUrl") and not valid_http_url(row.get("productUrl"))
            ),
            "image_url": bool(row.get("imageUrl") and not valid_http_url(row.get("imageUrl"))),
            "brand_provenance": bool(
                row.get("bn")
                and str(row.get("brandSource") or "").strip().lower()
                not in {"retailer", "gtin", "known_name"}
            ),
        }
        failed_contract_fields = [
            field for field, invalid in row_contract_errors.items() if invalid
        ]
        if failed_contract_fields:
            contract_errors += 1
            contract_error_reasons.update(failed_contract_fields)
        scraped = _scraped_at(row)
        if scraped is None:
            missing_scraped_at += 1
        else:
            newest_scrape = max(newest_scrape, scraped) if newest_scrape else scraped
            if scraped > now + timedelta(hours=1):
                future_scrape += 1
            elif (now - scraped).total_seconds() > thresholds["stale_after_hours"] * 3600:
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
            "future_timestamp_count": future_scrape,
            "newest_at": newest_scrape.isoformat() if newest_scrape else None,
        },
        "completeness": {
            "quantity_coverage": _rate(with_quantity, total),
            "unit_price_coverage": _rate(with_unit_price, with_quantity),
            "brand_coverage": _rate(with_brand, total),
            "category_coverage": _rate(with_category, total),
            "product_url_coverage": _rate(with_product_url, total),
            "image_url_coverage": _rate(with_image_url, total),
            "contract_error_count": contract_errors,
            "contract_error_reasons": dict(contract_error_reasons),
        },
        "malformed_rows": malformed_rows,
        "promo_in_name": promo_in_name,
    }
    result["metrics"] = metrics

    def issue(severity: str, code: str, actual: Any, threshold: Any) -> None:
        result["issues"].append(
            {"severity": severity, "code": code, "actual": actual, "threshold": threshold}
        )

    optional = bool(cfg.get("optional"))
    if total < thresholds["minimum_products"]:
        severity = "warning" if optional else "error"
        issue(severity, "product_count_below_minimum", total, thresholds["minimum_products"])
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
        issue("warning", "barcode_coverage_below_minimum", coverage, thresholds["minimum_barcode_coverage"])
    if invalid_barcode:
        issue("warning", "invalid_barcodes", invalid_barcode, 0)
    if missing_scraped_at:
        severity = "warning" if optional else "error"
        issue(severity, "missing_observation_timestamps", missing_scraped_at, 0)
    if stale_scrape:
        # Optional stores are best-effort; stale last-good rows should not fail CI.
        severity = "warning" if optional else "error"
        issue(severity, "stale_scrape_rows", stale_scrape, 0)
    if future_scrape:
        severity = "warning" if optional else "error"
        issue(severity, "future_observation_timestamps", future_scrape, 0)
    if malformed_rows or promo_in_name:
        issue("warning", "malformed_or_rejected_rows", malformed_rows + promo_in_name, 0)
    completeness = metrics["completeness"]
    if contract_errors:
        severity = "warning" if optional else "error"
        issue(severity, "data_contract_errors", contract_errors, 0)
    quantity_coverage = completeness["quantity_coverage"]
    if quantity_coverage < thresholds["minimum_quantity_coverage"]:
        severity = "warning" if optional else "error"
        issue(
            severity,
            "quantity_coverage_below_minimum",
            quantity_coverage,
            thresholds["minimum_quantity_coverage"],
        )
    elif quantity_coverage < thresholds["target_quantity_coverage"]:
        issue(
            "warning",
            "quantity_coverage_below_target",
            quantity_coverage,
            thresholds["target_quantity_coverage"],
        )
    if completeness["unit_price_coverage"] < thresholds["minimum_unit_price_coverage"]:
        severity = "warning" if optional else "error"
        issue(
            severity,
            "unit_price_coverage_below_minimum",
            completeness["unit_price_coverage"],
            thresholds["minimum_unit_price_coverage"],
        )
    for metric, threshold_key, code in (
        ("brand_coverage", "minimum_brand_coverage", "brand_coverage_below_minimum"),
        ("category_coverage", "minimum_category_coverage", "category_coverage_below_minimum"),
        ("product_url_coverage", "minimum_product_url_coverage", "product_url_coverage_below_minimum"),
        ("image_url_coverage", "minimum_image_url_coverage", "image_url_coverage_below_minimum"),
    ):
        if completeness[metric] < thresholds[threshold_key]:
            issue("warning", code, completeness[metric], thresholds[threshold_key])

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
