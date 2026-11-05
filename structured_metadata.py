"""Conservative, retailer-independent Product/Offer JSON-LD extraction.

No network requests. Aggregate, member-only, expired, unavailable and ambiguous
offers are deliberately not turned into a public shelf price.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin, urlsplit
from label_evidence import extract_label_evidence


def _type(node: dict, name: str) -> bool:
    values = node.get("@type", [])
    return name in [str(v).rsplit("/", 1)[-1] for v in (values if isinstance(values, list) else [values])]


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("value"))
    return ""


def _size(value: Any) -> str:
    if isinstance(value, dict) and value.get("value") is not None:
        unit = value.get("unitText") or {"GRM": "g", "KGM": "kg", "MLT": "ml", "LTR": "l"}.get(value.get("unitCode"))
        return f"{value['value']} {unit}" if unit else ""
    return _text(value)


def _url(value: Any, base_url: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        url = urljoin(base_url, value)
        parts, base = urlsplit(url), urlsplit(base_url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.netloc.lower() != base.netloc.lower() or parts.username or parts.password:
        return None
    return url if parts.path not in {"", "/"} else None


def extract_products(payload: Any, *, base_url: str, currency: str, now: datetime | None = None) -> list[dict]:
    """Flatten graphs/ItemLists and local @id links, with bounded traversal."""
    nodes: list[dict] = []
    pending = [payload]
    while pending and len(nodes) < 10000:
        value = pending.pop()
        if isinstance(value, dict):
            nodes.append(value)
            pending.extend(v for v in value.values() if isinstance(v, (list, dict)))
        elif isinstance(value, list):
            pending.extend(value[:10000])
    refs = {node["@id"]: node for node in nodes if isinstance(node.get("@id"), str) and len(node) > 1}
    def resolve(value: Any) -> Any:
        ref = value.get("@id") if isinstance(value, dict) else None
        return refs.get(ref, value) if isinstance(ref, str) else value
    now = now or datetime.now(timezone.utc)
    products = []
    seen = set()
    for node in nodes:
        if not _type(node, "Product"):
            continue
        name = _text(node.get("name"))
        raw_offers = resolve(node.get("offers"))
        raw_offers = raw_offers if isinstance(raw_offers, list) else [raw_offers]
        offers = []
        for candidate in raw_offers:
            offer = resolve(candidate)
            if not isinstance(offer, dict) or _type(offer, "AggregateOffer"):
                continue
            if str(offer.get("priceCurrency", "")).upper() != currency:
                continue
            # Absence of an availability claim is unknown, not "in stock".
            availability = str(offer.get("availability") or "").rsplit("/", 1)[-1]
            if availability and availability not in {"InStock", "LimitedAvailability", "OnlineOnly", "InStoreOnly"}:
                continue
            if offer.get("validForMemberTier") or offer.get("eligibleCustomerType"):
                continue
            if str(offer.get("itemCondition") or "").rsplit("/", 1)[-1] not in {"", "NewCondition"}:
                continue
            expired = False
            for key in ("priceValidUntil", "validThrough", "availabilityEnds"):
                if offer.get(key):
                    try:
                        date = datetime.fromisoformat(str(offer[key]).replace("Z", "+00:00"))
                        if len(str(offer[key])) == 10:
                            date = date.replace(hour=23, minute=59, second=59)
                        expired |= date.replace(tzinfo=date.tzinfo or timezone.utc) < now
                    except ValueError:
                        expired = True
            for key in ("validFrom", "availabilityStarts"):
                if offer.get(key):
                    try:
                        date = datetime.fromisoformat(str(offer[key]).replace("Z", "+00:00"))
                        expired |= date.replace(tzinfo=date.tzinfo or timezone.utc) > now
                    except ValueError:
                        expired = True
            if expired:
                continue
            try:
                price = Decimal(str(offer.get("price")))
                if not price.is_finite() or not 0 < price < 100000 or price.as_tuple().exponent < -2:
                    continue
            except (InvalidOperation, ValueError):
                continue
            url = _url(offer.get("url") or node.get("url") or node.get("@id"), base_url)
            if url:
                offers.append((price, url, availability))
        # Multiple sellers/variants with differing prices or URLs need a retailer adapter.
        unique = set(offers)
        if not name or len(unique) != 1:
            continue
        price, url, availability = unique.pop()
        key = (url, name, price)
        if key in seen:
            continue
        seen.add(key)
        image = node.get("image")
        image = image[0] if isinstance(image, list) and image else image
        image = image.get("url", "") if isinstance(image, dict) else image
        product = {
            "name": name, "price": f"{price:.2f}", "url": url,
            "image": image if isinstance(image, str) else "",
            "barcode": _text(node.get("gtin13") or node.get("gtin8") or node.get("gtin14") or node.get("gtin")),
            "retailer_product_id": _text(node.get("sku") or node.get("productID")),
            "brand": _text(node.get("brand")), "category": _text(node.get("category")),
            "size": _size(node.get("size") or node.get("netContent") or node.get("weight")),
            "availability": availability,
        }
        evidence = extract_label_evidence(node, source_url=url, observed_at=now.isoformat())
        if evidence:
            product["labelEvidence"] = evidence
        products.append(product)
    return products


def extract_page_products(page: Any, *, base_url: str, currency: str, factory: Any) -> list[dict]:
    """Use already-rendered scripts without adding per-product requests."""
    scripts = page.locator('script[type="application/ld+json"]')
    payloads = []
    remaining_bytes = 5_000_000
    try:
        for index in range(min(scripts.count(), 100)):
            try:
                raw = scripts.nth(index).inner_text(timeout=1000)
                if len(raw) <= min(2_000_000, remaining_bytes):
                    remaining_bytes -= len(raw)
                    payloads.append(json.loads(raw))
            except (ValueError, RecursionError):
                continue
    except Exception:
        return []
    rows = []
    for product in extract_products(payloads, base_url=base_url, currency=currency):
        evidence = product.pop("labelEvidence", None)
        row = factory(**product, base_url=base_url)
        if row:
            row["sourceMethod"] = "json_ld"
            if evidence:
                row["labelEvidence"] = evidence
            rows.append(row)
    return rows


def enrich_rows(rows: list[dict], metadata: list[dict]) -> list[dict]:
    """Fill missing attributes only for identical URLs and agreeing prices.

    API/DOM observations keep their price, timestamp and provenance. Never join
    on names alone: that can attach a different size/variant's barcode.
    """
    by_url: dict[str, list[dict]] = {}
    for item in metadata:
        url = item.get("productUrl") or item.get("i")
        if url:
            by_url.setdefault(url, []).append(item)
    for row in rows:
        matches = by_url.get(row.get("productUrl") or row.get("i"), [])
        if len(matches) != 1:
            continue
        match = matches[0]
        try:
            if Decimal(str(row.get("p"))) != Decimal(str(match.get("p"))):
                continue
        except InvalidOperation:
            continue
        for key in ("b", "s", "bn", "availability", "retailerProductId"):
            if not row.get(key) and match.get(key):
                row[key] = match[key]
                if key == "bn":
                    row["brandSource"] = "retailer"
        if match.get("labelEvidence"):
            row["labelEvidence"] = match["labelEvidence"]
    return rows
