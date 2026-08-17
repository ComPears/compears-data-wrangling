"""Normalize scraped UK grocery rows into the legacy seed catalog shape."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


def _repo_root() -> Path:
    p = Path(__file__).resolve().parent
    for _ in range(8):
        if (p / "config" / "stores.json").is_file():
            s = str(p)
            if s not in sys.path:
                sys.path.insert(0, s)
            return p
        p = p.parent
    raise RuntimeError("Could not find compears-data-wrangling root")


_repo_root()
from category_utils import ensure_canonical, infer_category_from_name, structured_with_category
from data_contract import parse_quantity
from product_sanitize import dedupe_by_identity


_PRICE_RE = re.compile(r"£?\s*(\d+(?:\.\d{1,2})?)")
_PENCE_RE = re.compile(r"(?<![\d.])(\d{1,3})\s*p\b", re.IGNORECASE)
def parse_gbp_price(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return f"{float(value):.2f}"
    text = str(value).strip()
    if not text:
        return None
    pence = _PENCE_RE.search(text.replace(",", ""))
    if pence and "£" not in text:
        amount = int(pence.group(1)) / 100
        return f"{amount:.2f}" if amount > 0 else None
    match = _PRICE_RE.search(text.replace(",", ""))
    if not match:
        return None
    amount = float(match.group(1))
    if amount <= 0:
        return None
    return f"{amount:.2f}"


def guess_size(name: str, size_hint: str | None = None) -> str:
    for candidate in (size_hint or "", name):
        quantity = parse_quantity(candidate)
        if quantity:
            return str(quantity["display"])
    return ""


def raw_product(
    *,
    name: str,
    price: Any,
    url: str | None = None,
    image: str | None = None,
    size: str | None = None,
    offer: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    base_url: str | None = None,
    retailer_product_id: str | None = None,
    availability: str | None = None,
    brand: Any = None,
) -> dict[str, Any] | None:
    clean_name = re.sub(r"\s+", " ", (name or "").strip())
    parsed_price = parse_gbp_price(price)
    if len(clean_name) < 3 or not parsed_price:
        return None

    product_url = url or ""
    if product_url and base_url and product_url.startswith("/"):
        product_url = urljoin(base_url, product_url)

    image_url = image or ""
    if image_url and base_url and image_url.startswith("/"):
        image_url = urljoin(base_url, image_url)

    cat = ensure_canonical(category) if category else infer_category_from_name(clean_name)
    if cat == "Other" and category:
        cat = infer_category_from_name(f"{category} {clean_name}")
    entry: dict[str, Any] = {
        "n": clean_name,
        "p": parsed_price,
        "o": (offer or "").strip(),
        "s": guess_size(clean_name, size),
        "l": image_url,
        "i": product_url,
        "c": cat,
        "currency": "GBP",
    }
    if product_url:
        entry["productUrl"] = product_url
    if image_url:
        entry["imageUrl"] = image_url
    if retailer_product_id:
        entry["retailerProductId"] = str(retailer_product_id).strip()
    if availability:
        entry["availability"] = str(availability).strip().lower()
    resolved_brand = brand.get("name") if isinstance(brand, dict) else brand
    if resolved_brand:
        entry["bn"] = str(resolved_brand).strip()
        entry["brandSource"] = "retailer"
    if barcode:
        entry["b"] = str(barcode).strip()
    return entry


def structure_raw_products(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    structured: list[dict[str, Any]] = []
    for item in raw_items:
        name = item.get("n") or item.get("name") or ""
        price = item.get("p") if "p" in item else item.get("price")
        entry = raw_product(
            name=str(name),
            price=price,
            url=item.get("i") or item.get("url"),
            image=item.get("l") or item.get("image"),
            size=item.get("s") or item.get("size"),
            offer=item.get("o") or item.get("offer"),
            barcode=item.get("b") or item.get("barcode"),
            category=item.get("c") or item.get("category"),
            retailer_product_id=item.get("retailerProductId") or item.get("sku") or item.get("id"),
            availability=item.get("availability"),
            brand=item.get("bn") or item.get("brand") or item.get("brandName"),
        )
        if not entry:
            continue
        for key in ("sourceQuery", "sourceUrl", "sourceMethod"):
            if item.get(key):
                entry[key] = item[key]
        sanitized = structured_with_category(entry, entry)
        if sanitized:
            structured.append(sanitized)
    deduped, _removed = dedupe_by_identity(structured)
    return deduped
