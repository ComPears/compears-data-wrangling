#!/usr/bin/env python3
"""Build auditable exact-match groups used by the comparison backend."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import all_catalog_paths, list_countries
from barcode_utils import normalize_barcode
from product_matching import canonical_product_id, score_match


def _load(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def build_country_from_catalogs(
    country: str,
    catalogs: list[tuple[str, Path]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_offers = 0
    for store, catalog in catalogs:
        for row in _load(catalog):
            total_offers += 1
            key = str(row.get("ik") or "").strip()
            if key:
                by_key[key].append({"store": store, **row})

    groups: list[dict[str, Any]] = []
    matched_offers = 0
    rejected_groups = 0
    for key, offers in by_key.items():
        stores = {str(offer["store"]) for offer in offers}
        if len(stores) < 2:
            continue
        method = "gtin" if key.startswith("ean:") else "normalized_attributes"
        if method == "gtin":
            expected_barcode = normalize_barcode(key.removeprefix("ean:"))
            eligible = bool(expected_barcode) and all(
                normalize_barcode(offer.get("b")) == expected_barcode for offer in offers
            )
            confidence = 1.0
        else:
            reference = offers[0]
            decisions = [score_match(reference, offer) for offer in offers[1:]]
            eligible = bool(decisions) and all(
                decision.auto_match and decision.method == "normalized_attributes"
                for decision in decisions
            )
            confidence = min((decision.confidence for decision in decisions), default=0.0)
        if not eligible:
            rejected_groups += 1
            continue
        selected = [
            {
                "retailer": offer["store"],
                "retailerProductId": offer.get("retailerProductId"),
                "name": offer.get("n"),
                "price": offer.get("p"),
                "currency": offer.get("currency"),
                "productUrl": offer.get("productUrl"),
                "observedAt": offer.get("observedAt"),
            }
            for offer in offers
        ]
        matched_offers += len(selected)
        groups.append(
            {
                "canonicalProductId": canonical_product_id(country, key),
                "matchKey": key,
                "method": method,
                "confidence": confidence,
                "offers": selected,
            }
        )

    groups.sort(key=lambda row: (-len(row["offers"]), row["canonicalProductId"]))
    report = {
        "schemaVersion": 1,
        "country": country,
        "groups": groups,
    }
    quality = {
        "country": country,
        "totalOffers": total_offers,
        "matchedOffers": matched_offers,
        "matchedOfferCoverage": round(matched_offers / total_offers, 6) if total_offers else 0,
        "groups": len(groups),
        "gtinGroups": sum(1 for group in groups if group["method"] == "gtin"),
        "rejectedGroups": rejected_groups,
    }
    return report, quality


def build_country(country: str) -> tuple[dict[str, Any], dict[str, Any]]:
    catalogs = [
        (store, catalog)
        for _country, store, catalog in all_catalog_paths(country)
    ]
    return build_country_from_catalogs(country, catalogs)


def main() -> int:
    output_dir = ROOT / "reports" / "matches"
    output_dir.mkdir(parents=True, exist_ok=True)
    quality: list[dict[str, Any]] = []
    for country in list_countries():
        report, country_quality = build_country(country)
        (output_dir / f"{country}.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        quality.append(country_quality)
        print(
            f"{country}: {country_quality['groups']} groups, "
            f"{country_quality['matchedOfferCoverage']:.1%} of offers comparable"
        )
    (ROOT / "reports" / "match-quality.json").write_text(
        json.dumps(quality, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
