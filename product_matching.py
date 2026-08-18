"""Conservative cross-retailer product matching with auditable confidence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from barcode_utils import normalize_barcode
from data_contract import quantity_fingerprint

AUTO_MATCH_THRESHOLD = 0.95
REVIEW_THRESHOLD = 0.80


@dataclass(frozen=True)
class MatchDecision:
    method: str
    confidence: float
    auto_match: bool
    reason: str


def _tokens(row: dict[str, Any]) -> set[str]:
    brand = str(row.get("bn") or "").strip().lower()
    text = str(row.get("cn") or row.get("n") or "").lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    tokens.difference_update(re.findall(r"[a-z0-9]+", brand))
    return tokens


def _brand(row: dict[str, Any]) -> str:
    if str(row.get("brandSource") or "").strip().lower() not in {
        "retailer",
        "gtin",
        "known_name",
    }:
        return ""
    return re.sub(r"\s+", " ", str(row.get("bn") or "").strip().lower())


def _quantity(row: dict[str, Any]) -> str:
    quantity = row.get("quantity")
    return quantity_fingerprint(quantity if isinstance(quantity, dict) else None)


def score_match(left: dict[str, Any], right: dict[str, Any]) -> MatchDecision:
    """Score a pair; only evidence-rich matches may be auto-published."""
    left_barcode = normalize_barcode(left.get("b"))
    right_barcode = normalize_barcode(right.get("b"))
    if left_barcode and right_barcode:
        if left_barcode == right_barcode:
            return MatchDecision("gtin", 1.0, True, "same validated GTIN")
        return MatchDecision("none", 0.0, False, "different validated GTINs")

    left_brand, right_brand = _brand(left), _brand(right)
    left_quantity, right_quantity = _quantity(left), _quantity(right)
    if not left_brand or not right_brand or left_brand != right_brand:
        return MatchDecision("none", 0.0, False, "brand is missing or differs")
    if left_quantity == "na" or right_quantity == "na":
        return MatchDecision("review", 0.70, False, "quantity is missing")
    if left_quantity != right_quantity:
        return MatchDecision("none", 0.0, False, "package quantity differs")

    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return MatchDecision("review", 0.70, False, "product variant tokens are missing")
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    if overlap == 1:
        return MatchDecision("normalized_attributes", 0.98, True, "same brand, variant and quantity")
    if overlap >= 0.90:
        return MatchDecision("normalized_attributes", 0.96, True, "near-identical variant tokens")
    if overlap >= 0.70:
        return MatchDecision("review", round(0.80 + (overlap - 0.70) * 0.5, 3), False, "ambiguous variant similarity")
    return MatchDecision("none", round(overlap, 3), False, "variant tokens differ")


def canonical_product_id(country: str, match_key: str) -> str:
    digest = hashlib.sha256(f"{country}|{match_key}".encode()).hexdigest()[:20]
    return f"cp_{digest}"
