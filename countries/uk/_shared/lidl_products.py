"""Read Lidl UK's product-tile metadata, not its accessibility/promotion text."""

from __future__ import annotations

import json
import math
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from playwright.sync_api import Page

from uk_product import raw_product

BASE_URL = "https://www.lidl.co.uk"


def product_from_tile(tile: dict[str, Any]) -> dict[str, Any] | None:
    try:
        metadata = json.loads(unquote(str(tile.get("metadata") or "")))
    except (ValueError, TypeError):
        return None
    if not isinstance(metadata, dict) or metadata.get("category") != "Food":
        # NonFood includes hardware, clothing and plants, even when a query
        # matches a food word (e.g. wing nuts). Unknown categories fail closed.
        return None
    product_id = str(metadata.get("id") or "")
    url = urlsplit(urljoin(BASE_URL, str(tile.get("href") or "")))
    if (url.scheme != "https" or url.netloc != "www.lidl.co.uk"
            or not re.fullmatch(r"\d+", product_id)
            or not re.fullmatch(r"/p/[^/]+/p" + product_id, url.path)):
        return None
    price = metadata.get("price")
    if (isinstance(price, bool) or not isinstance(price, (int, float))
            or not math.isfinite(price) or price <= 0):
        return None
    name = metadata.get("name")
    if not isinstance(name, str):
        return None
    text = str(tile.get("text") or "")
    offer = "Lidl Plus" if re.search(r"\bWith Lidl Plus\b", text, re.I) else None
    if not offer and re.search(r"\bSAVE\b", text):
        offer = "Retailer promotion"
    if re.search(r"(?m)^\s*\d+\s+for\s*$", text, re.I):
        # Tile metadata can contain the total multi-buy price (e.g. 2 for £6).
        # Publish the explicitly displayed single-item price, never that total.
        regular = re.search(r"\bRegular price\s*£\s*(\d+(?:\.\d{1,2})?)\b", text, re.I)
        if not regular:
            return None
        price = float(regular.group(1))
        offer = None
    availability_text = str(tile.get("availability") or "").strip()
    availability = None
    if "Available in store now" in availability_text:
        availability = "in_stock"
    elif "In store from" in availability_text:
        availability = "preorder"
    entry = raw_product(
        name=name, price=price,
        url=urlunsplit((url.scheme, url.netloc, url.path, "", "")),
        image=str(tile.get("image") or ""),
        # Only explicit title quantities: £/kg or £/l is a unit-price basis,
        # not proof that the item weighs 1 kg or contains 1 litre.
        size=name, brand=metadata.get("brand"),
        retailer_product_id=product_id, offer=offer,
        availability=availability,
    )
    if entry:
        entry["retailerCategory"] = "Food"
        entry["categorySource"] = "lidl_product_grid"
        if availability_text:
            entry["availabilityText"] = availability_text
    return entry


def extract_lidl_products(page: Page) -> list[dict[str, Any]]:
    # Header/navigation classes can satisfy the shared generic readiness check
    # before the Vue product grid has hydrated. Wait for actual tile metadata.
    page.locator("[data-gridbox-impression]").first.wait_for(state="attached", timeout=15000)
    tiles = page.locator("[data-gridbox-impression]").evaluate_all("""els => els.map(el => ({
        metadata: el.getAttribute('data-gridbox-impression'),
        href: el.querySelector('a[href*="/p/"]')?.href || '',
        image: el.querySelector('img')?.src || '',
        text: el.innerText || '',
        availability: el.querySelector('.product-grid-box__availabilities')?.innerText || ''
    }))""")
    return [product for tile in tiles if (product := product_from_tile(tile))]
