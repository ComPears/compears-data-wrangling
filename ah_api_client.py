"""Albert Heijn mobile API client (bypasses ah.nl bot protection in CI)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://api.ah.nl"
USER_AGENT = "Appie/8.22.3"
APPLICATION = "AHWEBSHOP"
PAGE_SIZE = 50
MAX_RETRIES = 3
RETRY_DELAY = 2.0


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
            if err.code in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
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

    return {"raw_text": "\n".join(lines), "image": _image_url(product)}


def fetch_taxonomy_products(token: str, taxonomy_id: str) -> list[dict[str, Any]]:
    """Fetch all products for a top-level AH taxonomy category."""
    products: list[dict[str, Any]] = []
    page = 0

    while True:
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
        time.sleep(0.2)

    return products
