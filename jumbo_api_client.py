"""Jumbo GraphQL API client (replaces fragile Playwright pagination in CI)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from urllib.parse import urlparse

GRAPHQL_URL = "https://www.jumbo.com/api/graphql"
PAGE_SIZE = 24
MAX_RETRIES = 3
RETRY_DELAY = 2.0

SEARCH_PRODUCTS_QUERY = """
query SearchProducts($input: ProductSearchInput!) {
  searchProducts(input: $input) {
    count
    products {
      id: sku
      title
      image
      link
      prices: price {
        price
        promoPrice
      }
      promotions {
        tags {
          text
        }
      }
    }
  }
}
"""

GRAPHQL_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "nl-NL,nl;q=0.9",
    "apollographql-client-name": "JUMBO_WEB-search",
    "apollographql-client-version": "master-v30.4.0-web",
    "x-source": "JUMBO_WEB-search",
}


class JumboApiError(RuntimeError):
    """Raised when the Jumbo GraphQL API returns an error response."""


def _graphql_request(body: dict[str, Any]) -> Any:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL, data=data, headers=GRAPHQL_HEADERS, method="POST"
    )

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("errors"):
                raise JumboApiError(str(payload["errors"])[:300])
            return payload.get("data")
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")
            last_error = JumboApiError(f"HTTP {err.code}: {detail[:300]}")
            if err.code in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
                continue
            raise last_error from err
        except urllib.error.URLError as err:
            last_error = JumboApiError(f"Network error: {err}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
                continue
            raise last_error from err

    raise last_error or JumboApiError("GraphQL request failed")


def _search_input(url: str, offset: int) -> dict[str, Any]:
    parsed = urlparse(url)
    slug = parsed.path.removeprefix("/producten/").strip("/")

    if parsed.path.startswith("/producten"):
        if slug:
            friendly = f"{slug}/?offSet={offset}"
            current = f"/producten/{slug}/?offSet={offset}"
        else:
            query = parsed.query
            friendly = f"?{query}&offSet={offset}" if query else f"?offSet={offset}"
            current = f"/producten/?{query}&offSet={offset}" if query else f"/producten/?offSet={offset}"
    else:
        path_slug = parsed.path.strip("/")
        friendly = f"{path_slug}/?offSet={offset}"
        current = f"{parsed.path.rstrip('/')}/?offSet={offset}"

    return {
        "searchType": "category",
        "searchTerms": "producten",
        "friendlyUrl": friendly,
        "offSet": offset,
        "currentUrl": current,
        "previousUrl": "",
    }


def supports_api_scrape(url: str) -> bool:
    """GraphQL category search only works for /producten/{slug}/ pages."""
    parsed = urlparse(url)
    if not parsed.path.startswith("/producten/"):
        return False
    slug = parsed.path.removeprefix("/producten/").strip("/")
    return bool(slug) and "?" not in slug


def _discount_text(product: dict[str, Any]) -> str | None:
    promotions = product.get("promotions") or []
    if not promotions:
        return None
    tags = promotions[0].get("tags") or []
    if not tags:
        return None
    text = tags[0].get("text")
    return text if isinstance(text, str) else None


def _format_price(cents: int | float | None) -> str:
    if cents is None:
        return ""
    value = float(cents) / 100.0
    whole, frac = f"{value:.2f}".split(".")
    return f"Prijs: € {whole},{frac}"


def product_to_raw_entry(product: dict[str, Any]) -> dict[str, str | None]:
    """Convert a Jumbo GraphQL product to the raw_text format expected by structure.py."""
    title = (product.get("title") or "").strip()
    prices = product.get("prices") or {}
    promo_cents = prices.get("promoPrice")
    base_cents = prices.get("price")
    active_cents = promo_cents if promo_cents is not None else base_cents

    lines = [title]
    discount = _discount_text(product)
    if discount:
        lines.append(discount)
    price_line = _format_price(active_cents)
    if price_line:
        lines.append(price_line)

    return {
        "raw_text": "\n".join(lines),
        "image": product.get("image"),
        "link": product.get("link"),
    }


def fetch_category_products(url: str) -> list[dict[str, Any]]:
    """Fetch all products for a Jumbo category URL via GraphQL pagination."""
    products: list[dict[str, Any]] = []
    offset = 0
    total_count: int | None = None

    while True:
        data = _graphql_request(
            {
                "operationName": "SearchProducts",
                "variables": {"input": _search_input(url, offset)},
                "query": SEARCH_PRODUCTS_QUERY,
            }
        )
        result = (data or {}).get("searchProducts") or {}
        if total_count is None:
            total_count = int(result.get("count") or 0)
        batch = result.get("products") or []
        products.extend(batch)

        if not batch or offset + PAGE_SIZE >= total_count:
            break
        offset += PAGE_SIZE
        time.sleep(0.15)

    return products
