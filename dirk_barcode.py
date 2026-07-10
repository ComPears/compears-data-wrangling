"""EAN extraction from Dirk product-card source schema."""

from __future__ import annotations

import json
from typing import Any

from barcode_utils import extract_barcode_from_entry


def extract_card_barcode(card: Any) -> str | None:
    """Read explicit data attributes and Product JSON-LD from a Dirk card."""
    explicit = {
        "ean": card.get_attribute("data-ean"),
        "gtin": card.get_attribute("data-gtin"),
        "barcode": card.get_attribute("data-product-ean"),
    }
    barcode = extract_barcode_from_entry(explicit)
    if barcode:
        return barcode

    for script in card.query_selector_all('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.text_content() or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            barcode = extract_barcode_from_entry(payload)
            if barcode:
                return barcode
    return None
