#!/usr/bin/env python3
"""Validate canonical JSON and emit a data-quality report."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, catalog_rel_path, store_config
from category_utils import CANONICAL_CATEGORIES
from data_contract import is_valid_quantity, is_valid_unit_price, valid_http_url
from product_sanitize import should_reject_name


def validate_file(country: str, slug: str, catalog: Path) -> dict:
    rel_path = catalog_rel_path(country, slug)
    cfg = store_config(country, slug)
    report = {
        "country": country,
        "store": slug,
        "quality_profile_version": int(cfg.get("quality_profile_version") or 1),
        "total": 0,
        "with_barcode": 0,
        "with_identity": 0,
        "with_brand": 0,
        "with_weight": 0,
        "with_quantity": 0,
        "with_unit_price": 0,
        "with_observed_at": 0,
        "with_product_url": 0,
        "with_image_url": 0,
        "promo_in_name": 0,
        "missing_price": 0,
        "missing_url": 0,
        "duplicate_identity": 0,
        "contract_errors": 0,
    }
    if not catalog.exists():
        return report

    with open(catalog, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return report

    report["total"] = len(data)
    identity_counts: Counter[str] = Counter()

    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("n") or "")
        if should_reject_name(name):
            report["promo_in_name"] += 1
        price = str(entry.get("p") or "").strip()
        if not price or price in {"0", "0.0", "0.00"}:
            report["missing_price"] += 1
        if not valid_http_url(entry.get("productUrl")):
            report["missing_url"] += 1
        else:
            report["with_product_url"] += 1
        if valid_http_url(entry.get("imageUrl")):
            report["with_image_url"] += 1
        if entry.get("b"):
            report["with_barcode"] += 1
        if entry.get("ik"):
            report["with_identity"] += 1
            identity_counts[str(entry["ik"])] += 1
        if entry.get("bn"):
            report["with_brand"] += 1
        if entry.get("wg"):
            report["with_weight"] += 1
        quantity = entry.get("quantity")
        quantity_valid = is_valid_quantity(quantity)
        if quantity_valid:
            report["with_quantity"] += 1
        expected_currency = {"nl": "EUR", "de": "EUR", "uk": "GBP"}.get(country)
        unit_price_valid = bool(
            quantity_valid
            and expected_currency
            and is_valid_unit_price(
                entry.get("unitPrice"),
                price=price,
                currency=expected_currency,
                quantity=quantity,
            )
        )
        if unit_price_valid:
            report["with_unit_price"] += 1
        if entry.get("observedAt"):
            report["with_observed_at"] += 1
        if (
            entry.get("schemaVersion") != 2
            or entry.get("country") != country
            or entry.get("retailer") != slug
            or entry.get("currency") != expected_currency
            or entry.get("priceType") not in {"regular", "promotion", "loyalty"}
            or entry.get("c") not in CANONICAL_CATEGORIES
            or (isinstance(quantity, dict) and not quantity_valid)
            or (quantity_valid and not unit_price_valid)
            or (entry.get("productUrl") and not valid_http_url(entry.get("productUrl")))
            or (entry.get("imageUrl") and not valid_http_url(entry.get("imageUrl")))
            or (
                entry.get("bn")
                and str(entry.get("brandSource") or "").strip().lower()
                not in {"retailer", "gtin", "known_name"}
            )
        ):
            report["contract_errors"] += 1

    report["duplicate_identity"] = sum(c - 1 for c in identity_counts.values() if c > 1)
    return report


def quantity_coverage_messages(report: dict, cfg: dict) -> tuple[str | None, str | None]:
    """Return a hard failure or an improvement warning for quantity coverage.

    The hard floor protects against a broken extraction. The higher target tracks
    expected data quality without rejecting a valid catalog when a retailer omits
    package sizes from a portion of its daily assortment.
    """
    total = int(report.get("total") or 0)
    if not total:
        return None, None

    minimum = float(cfg.get("minimum_quantity_coverage", 0.90))
    target = float(cfg.get("target_quantity_coverage", 0.90))
    label = f"{report['country']}/{report['store']}"
    if not 0 <= minimum <= target <= 1:
        return (
            f"{label}: invalid quantity coverage thresholds "
            f"(minimum={minimum:.1%}, target={target:.1%})",
            None,
        )

    coverage = int(report.get("with_quantity") or 0) / total
    if coverage < minimum:
        return (
            f"{label}: quantity coverage {coverage:.4%} below hard floor {minimum:.4%} "
            f"({int(report.get('with_quantity') or 0)}/{total} products)",
            None,
        )
    if coverage < target:
        return (
            None,
            f"WARNING: {label}: quantity coverage {coverage:.4%} below target {target:.4%}",
        )
    return None, None


def main() -> None:
    reports = []
    for country, slug, catalog in all_catalog_paths():
        reports.append(validate_file(country, slug, catalog))

    out_path = ROOT / "data-quality-report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2)

    print("| Country | Store | Total | Barcode | Identity | Brand | Quantity | Observed | Promo | Dup ik |")
    print("|---------|-------|------:|--------:|---------:|------:|---------:|---------:|------:|-------:|")
    for r in reports:
        total = r["total"] or 1
        bc_pct = f"{100 * r['with_barcode'] / total:.0f}%"
        print(
            f"| {r['country']} | {r['store']} | {r['total']} | {r['with_barcode']} ({bc_pct}) | "
            f"{r['with_identity']} | {r['with_brand']} | {r['with_quantity']} | "
            f"{r['with_observed_at']} | {r['promo_in_name']} | {r['duplicate_identity']} |"
        )

    failures: list[str] = []
    for report in reports:
        if store_config(report["country"], report["store"]).get("optional"):
            continue
        total = int(report["total"] or 0)
        if not total:
            failures.append(f"{report['country']}/{report['store']}: empty catalog")
            continue
        if report["missing_price"]:
            failures.append(
                f"{report['country']}/{report['store']}: {report['missing_price']} missing prices"
            )
        if report["contract_errors"]:
            failures.append(
                f"{report['country']}/{report['store']}: {report['contract_errors']} contract errors"
            )
        if report["with_observed_at"] != total:
            failures.append(
                f"{report['country']}/{report['store']}: missing observation timestamps"
            )
        cfg = store_config(report["country"], report["store"])
        quantity_failure, quantity_warning = quantity_coverage_messages(report, cfg)
        if quantity_failure:
            failures.append(quantity_failure)
        elif quantity_warning:
            print(quantity_warning)
        if report["promo_in_name"]:
            failures.append(
                f"{report['country']}/{report['store']}: promotion text remains in product names"
            )
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        sys.exit(1)


if __name__ == "__main__":
    main()
