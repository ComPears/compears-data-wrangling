"""Versioned product-offer contract shared by every country adapter.

The legacy catalogs use compact keys consumed by the backend.  This module
adds explicit, typed fields without removing those keys, so collection and
matching quality can improve without a flag-day migration.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlparse

SCHEMA_VERSION = 2
MIN_PRICE = Decimal("0.05")
MAX_PRICE = Decimal("500.00")

_MULTIPACK_RE = re.compile(
    r"(?P<count>\d+)\s*[x×]\s*(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>fl\s*oz|kg|g|ml|cl|l|oz|lbs?|pints?|liters?|litres?)\b",
    re.IGNORECASE,
)
_QUANTITY_RE = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>fl\s*oz|kg|g|ml|cl|l|oz|lbs?|pints?|liters?|litres?|"
    r"stuks?|stücks?|st\.?|pieces?|pcs?|packs?|pk|ct|items?|bags?|"
    r"capsules?|tablets?|rolls?)\b",
    re.IGNORECASE,
)
_IMAGE_HINTS = (
    "image",
    "images",
    "imgproxy",
    "scene7",
    "cloudfront",
    "ctfassets",
    "static.ah",
    "dam-images",
    "web-fileserver",
    "assets/",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".avif",
)


def utc_iso(value: str | datetime | None = None) -> str | None:
    """Return a validated UTC ISO timestamp, or ``None`` for invalid input."""
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_price(
    value: Any,
    *,
    maximum: Decimal = MAX_PRICE,
) -> tuple[str | None, str | None]:
    """Normalize a positive retail price and explain rejected values."""
    if value in (None, ""):
        return None, "missing_price"
    raw = str(value).strip().replace("€", "").replace("£", "").replace(" ", "")
    if not raw:
        return None, "missing_price"
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not match:
        return None, "invalid_price"
    try:
        price = Decimal(match.group(0))
    except InvalidOperation:
        return None, "invalid_price"
    if not price.is_finite() or price <= 0:
        return None, "invalid_price"
    if price < MIN_PRICE or price > maximum:
        return None, "implausible_price"
    return str(price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), None


def _number(value: float) -> int | float:
    rounded = round(value, 6)
    return int(rounded) if math.isclose(rounded, round(rounded)) else rounded


def _unit_details(value: float, unit: str) -> tuple[float, str, str]:
    normalized = unit.lower().rstrip(".")
    if normalized in {"liter", "liters", "litre", "litres"}:
        normalized = "l"
    if normalized == "kg":
        return value * 1000, "g", "kg"
    if normalized == "oz":
        return value * 28.349523125, "g", "oz"
    if normalized in {"lb", "lbs"}:
        return value * 453.59237, "g", "lb"
    if normalized.replace(" ", "") == "floz":
        return value * 28.4130625, "ml", "fl oz"
    if normalized in {"pint", "pints"}:
        return value * 568.26125, "ml", "pint"
    if normalized == "cl":
        return value * 10, "ml", "cl"
    if normalized == "l":
        return value * 1000, "ml", "l"
    if normalized in {
        "stuk",
        "stuks",
        "stück",
        "stücks",
        "st",
        "piece",
        "pieces",
        "pc",
        "pcs",
        "pack",
        "packs",
        "pk",
        "ct",
        "item",
        "items",
        "bag",
        "bags",
        "capsule",
        "capsules",
        "tablet",
        "tablets",
        "roll",
        "rolls",
    }:
        return value, "count", "count"
    return value, normalized, normalized


def is_valid_quantity(value: Any) -> bool:
    """Return whether a quantity has a coherent, comparable typed shape."""
    if not isinstance(value, dict):
        return False
    required = {"packCount", "itemValue", "itemUnit", "totalValue", "baseUnit"}
    if not required.issubset(value):
        return False
    try:
        pack_count = int(value["packCount"])
        item_value = float(value["itemValue"])
        total_value = float(value["totalValue"])
    except (TypeError, ValueError, OverflowError):
        return False
    if (
        isinstance(value["packCount"], bool)
        or pack_count < 1
        or not math.isfinite(item_value)
        or not math.isfinite(total_value)
        or item_value <= 0
        or total_value <= 0
    ):
        return False
    converted, base_unit, _item_unit = _unit_details(item_value, str(value["itemUnit"]))
    if base_unit not in {"g", "ml", "count"} or str(value["baseUnit"]) != base_unit:
        return False
    return math.isclose(total_value, pack_count * converted, rel_tol=1e-6, abs_tol=1e-6)


def parse_quantity(
    size: str | None,
    *,
    name: str | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Parse mass, volume, count and multipacks without conflating their units."""
    if is_valid_quantity(existing):
        return dict(existing)

    candidates = [str(size or ""), str(name or "")]
    for candidate in candidates:
        text = re.sub(r"^\s*per\s+", "", candidate.lower()).replace(",", ".")
        multi = _MULTIPACK_RE.search(text)
        if multi:
            count = int(multi.group("count"))
            item_value = float(multi.group("value"))
            if count < 1 or item_value <= 0:
                continue
            raw_unit = multi.group("unit").lower()
            base_value, base_unit, item_unit = _unit_details(item_value, raw_unit)
            total = count * base_value
            return {
                "packCount": count,
                "itemValue": _number(item_value),
                "itemUnit": item_unit,
                "totalValue": _number(total),
                "baseUnit": base_unit,
                "display": f"{count} × {_number(item_value)} {item_unit}",
            }

        match = _QUANTITY_RE.search(text)
        if not match:
            continue
        value = float(match.group("value"))
        raw_unit = match.group("unit").lower()
        base_value, base_unit, item_unit = _unit_details(value, raw_unit)
        if value <= 0:
            continue
        if base_unit == "count":
            if not value.is_integer():
                continue
            return {
                "packCount": int(value),
                "itemValue": 1,
                "itemUnit": "count",
                "totalValue": _number(base_value),
                "baseUnit": "count",
                "display": f"{_number(value)} items",
            }
        return {
            "packCount": 1,
            "itemValue": _number(value),
            "itemUnit": item_unit,
            "totalValue": _number(base_value),
            "baseUnit": base_unit,
            "display": f"{_number(value)} {item_unit}",
        }
    return None


def quantity_fingerprint(quantity: dict[str, Any] | None) -> str:
    if not quantity:
        return "na"
    count = int(quantity.get("packCount") or 1)
    item_value = quantity.get("itemValue")
    item_unit = str(quantity.get("itemUnit") or quantity.get("baseUnit") or "")
    total = quantity.get("totalValue")
    base_unit = str(quantity.get("baseUnit") or "")
    if count > 1 and item_value not in (None, ""):
        return f"{count}x{item_value}{item_unit}"
    return f"{total}{base_unit}" if total not in (None, "") else "na"


def unit_price(price: str, currency: str, quantity: dict[str, Any] | None) -> dict[str, str] | None:
    if not is_valid_quantity(quantity):
        return None
    try:
        amount = Decimal(price)
        total = Decimal(str(quantity.get("totalValue")))
    except (InvalidOperation, TypeError):
        return None
    if total <= 0:
        return None
    base_unit = str(quantity.get("baseUnit") or "")
    if base_unit == "g":
        value, per = amount * Decimal(1000) / total, "kg"
    elif base_unit == "ml":
        value, per = amount * Decimal(1000) / total, "l"
    elif base_unit == "count":
        value, per = amount / total, "item"
    else:
        return None
    return {
        "value": str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "currency": currency,
        "per": per,
    }


def is_valid_unit_price(
    value: Any,
    *,
    price: str,
    currency: str,
    quantity: dict[str, Any] | None,
) -> bool:
    """Validate that a stored unit price agrees with price and typed quantity."""
    if not isinstance(value, dict):
        return False
    expected = unit_price(price, currency, quantity)
    if not expected:
        return False
    try:
        actual_amount = Decimal(str(value.get("value")))
        expected_amount = Decimal(expected["value"])
    except (InvalidOperation, TypeError):
        return False
    return (
        actual_amount.is_finite()
        and abs(actual_amount - expected_amount) <= Decimal("0.01")
        and value.get("currency") == expected["currency"]
        and value.get("per") == expected["per"]
    )


def is_image_url(value: str | None) -> bool:
    url = str(value or "").strip().lower()
    return bool(url) and any(hint in url for hint in _IMAGE_HINTS)


def valid_http_url(value: str | None) -> str | None:
    url = str(value or "").strip()
    if not url:
        return None
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


def resolve_urls(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    product_url = valid_http_url(entry.get("productUrl") or entry.get("url"))
    image_url = valid_http_url(entry.get("imageUrl") or entry.get("image"))
    for key in ("i", "l"):
        candidate = valid_http_url(entry.get(key))
        if not candidate:
            continue
        if is_image_url(candidate):
            image_url = image_url or candidate
        else:
            product_url = product_url or candidate
    return product_url, image_url
