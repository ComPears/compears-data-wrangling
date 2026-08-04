"""Albert Heijn mobile API client (bypasses ah.nl bot protection in CI)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from concurrent.futures import ThreadPoolExecutor, as_completed

from barcode_utils import extract_barcode_from_entry

API_BASE = "https://api.ah.nl"
USER_AGENT = "Appie/8.22.3"
APPLICATION = "AHWEBSHOP"
PAGE_SIZE = 50
MAX_RETRIES = 3
RETRY_DELAY = 2.0
# AH search caps around page 60; split only when pagination fails.
MAX_SAFE_PAGES = 55
# Detail enrichment is one request per product; cap runtime while keeping yield useful.
DEFAULT_DETAIL_ENRICH_LIMIT = 5000
DEFAULT_DETAIL_WORKERS = 3
DETAIL_ENRICH_DELAY = 0.15


class AhApiError(RuntimeError):
    """Raised when the AH API returns an error response."""


def _request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    url = f"{API_BASE}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "X-Application": APPLICATION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            payload = err.read().decode("utf-8", errors="replace")
            last_error = AhApiError(f"HTTP {err.code} for {path}: {payload[:300]}")
            if err.code in {403, 429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt * (3 if err.code == 403 else 1))
                continue
            raise last_error from err
        except urllib.error.URLError as err:
            last_error = AhApiError(f"Network error for {path}: {err}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
                continue
            raise last_error from err

    raise last_error or AhApiError(f"Failed to call {path}")


def get_anonymous_token() -> str:
    payload = _request(
        "POST",
        "/mobile-auth/v1/auth/token/anonymous",
        body={"clientId": "appie"},
    )
    token = payload.get("access_token")
    if not token:
        raise AhApiError("Anonymous auth response missing access_token")
    return token


def taxonomy_id_from_url(url: str) -> str | None:
    match = re.search(r"/producten/(\d+)/", url)
    return match.group(1) if match else None


def _image_url(product: dict[str, Any]) -> str | None:
    images = product.get("images") or []
    if not images:
        return None
    first = images[0]
    if isinstance(first, dict):
        return first.get("url") or first.get("href")
    if isinstance(first, str):
        return first
    return None


def _webshop_id(product: dict[str, Any]) -> str | None:
    for key in ("webshopId", "id", "productId"):
        value = product.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def barcode_from_detail_payload(detail: dict[str, Any] | None) -> str | None:
    """Extract GTIN/EAN from a product/detail/v4 response (or nested card)."""
    if not isinstance(detail, dict):
        return None

    candidates: list[dict[str, Any]] = [detail]
    for key in ("productCard", "product", "card", "tradeItem"):
        nested = detail.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)

    trade_items = detail.get("tradeItems") or detail.get("tradeItemNumbers")
    if isinstance(trade_items, list):
        for item in trade_items:
            if isinstance(item, dict):
                candidates.append(item)

    for candidate in candidates:
        barcode = extract_barcode_from_entry(candidate)
        if barcode:
            return barcode
    return None


def fetch_product_detail(token: str, webshop_id: str | int) -> dict[str, Any]:
    """Fetch AH product detail by webshopId (includes GTIN when API provides it)."""
    payload = _request(
        "GET",
        f"/mobile-services/product/detail/v4/fir/{webshop_id}",
        token=token,
        params={"includeActivatableDiscount": "false"},
    )
    if not isinstance(payload, dict):
        raise AhApiError(f"Unexpected detail payload for {webshop_id}")
    return payload


def product_to_raw_entry(product: dict[str, Any]) -> dict[str, str | None]:
    """Convert an AH API product to the raw_text format expected by struc.py."""
    title = (product.get("title") or "").strip()
    brand = (product.get("brand") or "").strip()
    name = f"{brand} {title}".strip() if brand else title

    current_price = product.get("currentPrice")
    price_before_bonus = product.get("priceBeforeBonus")
    unit = (product.get("salesUnitSize") or "").strip()

    lines = [name]
    if product.get("isBonus"):
        mechanism = (product.get("bonusMechanism") or "").strip()
        if mechanism:
            lines.append(mechanism)
        elif price_before_bonus:
            lines.append(f"van {price_before_bonus:.2f}".replace(".", ","))

    price_value = current_price if current_price not in (None, 0) else price_before_bonus
    if price_value is not None:
        lines.append(f"{price_value:.2f}".replace(".", ","))

    if unit:
        lines.append(unit)

    barcode = extract_barcode_from_entry(product) or barcode_from_detail_payload(product)
    entry: dict[str, str | None] = {
        "raw_text": "\n".join(lines),
        "image": _image_url(product),
        # AH search responses usually omit GTIN; webshopId is not an EAN.
        # Prefer named EAN/GTIN fields only (detail enrichment fills the rest).
        "barcode": barcode,
    }
    webshop_id = _webshop_id(product)
    if webshop_id:
        entry["webshopId"] = webshop_id
    return entry


def enrich_raw_entries_with_detail_barcodes(
    token: str,
    entries: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_DETAIL_ENRICH_LIMIT,
    workers: int = DEFAULT_DETAIL_WORKERS,
) -> int:
    """Fill missing barcodes via product detail calls. Returns number enriched."""
    if limit <= 0:
        return 0

    targets: list[tuple[int, str]] = []
    for index, entry in enumerate(entries):
        if entry.get("barcode"):
            continue
        webshop_id = entry.get("webshopId")
        if not webshop_id:
            continue
        targets.append((index, str(webshop_id)))
        if len(targets) >= limit:
            break

    if not targets:
        return 0

    enriched = 0
    workers = max(1, min(workers, 3))

    def _lookup(webshop_id: str) -> str | None:
        try:
            detail = fetch_product_detail(token, webshop_id)
            time.sleep(DETAIL_ENRICH_DELAY)
            return barcode_from_detail_payload(detail)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_lookup, webshop_id): index for index, webshop_id in targets
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                barcode = future.result()
            except Exception:
                continue
            if barcode:
                entries[index]["barcode"] = barcode
                enriched += 1

    return enriched


def _taxonomy_child_ids(payload: dict[str, Any]) -> list[str]:
    for entry in payload.get("filters") or []:
        if entry.get("id") != "taxonomy":
            continue
        options = entry.get("options") or []
        return [str(option["id"]) for option in options if option.get("id")]
    return []


def _fetch_paginated(token: str, taxonomy_id: str) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    page = 0

    while page < MAX_SAFE_PAGES:
        payload = _request(
            "GET",
            "/mobile-services/product/search/v2",
            token=token,
            params={
                "taxonomyId": taxonomy_id,
                "adType": "TAXONOMY",
                "sortOn": "RELEVANCE",
                "page": page,
                "size": PAGE_SIZE,
            },
        )
        batch = payload.get("products") or []
        products.extend(batch)

        page_info = payload.get("page") or {}
        total_pages = page_info.get("totalPages", 1)
        if page + 1 >= total_pages or not batch:
            break
        page += 1
        time.sleep(0.5)

    return products


def fetch_taxonomy_products(token: str, taxonomy_id: str) -> list[dict[str, Any]]:
    """Fetch all products for an AH taxonomy, splitting on pagination limits."""
    try:
        return _fetch_paginated(token, taxonomy_id)
    except AhApiError as err:
        if "HTTP 400" not in str(err):
            raise

        probe = _request(
            "GET",
            "/mobile-services/product/search/v2",
            token=token,
            params={
                "taxonomyId": taxonomy_id,
                "adType": "TAXONOMY",
                "sortOn": "RELEVANCE",
                "page": 0,
                "size": 1,
            },
        )
        child_ids = _taxonomy_child_ids(probe)
        if not child_ids:
            raise AhApiError(
                f"Taxonomy {taxonomy_id} failed pagination and has no child filters"
            ) from err

        products: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for child_id in child_ids:
            for product in _fetch_paginated(token, child_id):
                product_id = str(product.get("id") or product.get("webshopId") or "")
                dedupe_key = product_id or json.dumps(product, sort_keys=True)
                if dedupe_key in seen_ids:
                    continue
                seen_ids.add(dedupe_key)
                products.append(product)
            time.sleep(0.05)

        return products
