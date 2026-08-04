"""Fast PLUS product-list scraper via intercepted PLP API responses."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from barcode_utils import (
    extract_barcode_from_entry,
    extract_barcode_from_html,
    extract_barcode_from_next_data,
)
from scrape_utils import PLUS_USER_AGENT

PRODUCT_CARD_SELECTOR = ".plp-item-wrapper"
PLP_API_FRAGMENT = "DataActionGetProductListAndCategoryInfo"
PLUS_ORIGIN = "https://www.plus.nl"
# Documented middleware detail API (may be unavailable; PDP HTML is the fallback).
PLUS_PRODUCT_API = "https://pls-sprmrkt-mw.prd.vdc1.plus.nl/api/v3/product/{product_id}"
MAX_API_PAGES = 250
DEFAULT_PDP_ENRICH_LIMIT = 1500
DEFAULT_PDP_WORKERS = 3
PDP_ENRICH_DELAY = 0.2


def resolve_redirect_url(url: str, *, timeout: int = 30) -> str:
    """Follow redirects and return the final URL (coop.nl -> plus.nl)."""
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": PLUS_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl()
    except urllib.error.HTTPError as err:
        if err.headers.get("Location"):
            return err.headers["Location"]
        raise


def is_generic_plus_listing(url: str) -> bool:
    """True when the redirect target is the site-wide product index."""
    path = urlparse(url).path.rstrip("/")
    return path in ("", "/producten")


def plus_cache_key(source_url: str, plus_url: str) -> str:
    """Cache key for COOP→PLUS redirects; avoid sharing the root /producten listing."""
    if is_generic_plus_listing(plus_url):
        return f"{source_url}|{plus_url}"
    return plus_url


def resolve_redirect_urls(urls: list[str], *, workers: int = 16) -> dict[str, str]:
    """Resolve many redirect URLs concurrently."""
    results: dict[str, str] = {}

    def _resolve(url: str) -> tuple[str, str]:
        return url, resolve_redirect_url(url)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_resolve, url) for url in urls]
        for future in as_completed(futures):
            source, target = future.result()
            results[source] = target

    return results


def dismiss_plus_modals(page: Page) -> None:
    """Close cookie banners and popup backdrops that block interaction."""
    for selector in (
        "button:has-text('Accepteren')",
        "button:has-text('Alles accepteren')",
        "button:has-text('Akkoord')",
    ):
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=1500):
                button.click(force=True)
                page.wait_for_timeout(400)
        except Exception:
            pass

    page.evaluate(
        "document.querySelectorAll('[data-popup-backdrop]').forEach(el => el.remove())"
    )
    page.wait_for_timeout(200)

    try:
        page.get_by_role("link", name="Sluit winkel keuze").click(timeout=1500)
        page.wait_for_timeout(300)
    except Exception:
        pass


def _with_pagina(url: str, page_num: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query.pop("pagina", None)
    if page_num > 1:
        query["pagina"] = [str(page_num)]
    flat = {key: values[0] for key, values in query.items()}
    return urlunparse(parsed._replace(query=urlencode(flat)))


def _format_price(value: str | float | int | None) -> str:
    if value in (None, "", "0", "0.0", 0, 0.0):
        return ""
    text = str(value).replace(".", ",")
    if "," not in text and text.isdigit():
        return f"{text},00"
    return text


def _product_from_plp(plp: dict) -> dict[str, str | None]:
    brand = (plp.get("Brand") or "").strip()
    name = (plp.get("Name") or "").strip()
    title = f"{brand} {name}".strip() if brand else name
    subtitle = (plp.get("Product_Subtitle") or "").strip()
    promo = _format_price(plp.get("NewPrice"))
    base = _format_price(plp.get("OriginalPrice"))
    price = promo or base

    lines = [line for line in (title, subtitle, price) if line]
    product_id = plp.get("ProductId")
    if product_id in (None, ""):
        product_id = plp.get("Product_Code")
    return {
        "raw_text": "\n".join(lines),
        "image": plp.get("ImageURL"),
        # Product_Code and image asset IDs are PLUS internal identifiers, not
        # EANs. Only consume explicit EAN/GTIN fields from PLP_Str; PDP
        # enrichment may accept a Product_Code that looks like a real GTIN.
        "barcode": extract_barcode_from_entry(plp),
        "link": (
            f"{PLUS_ORIGIN}/producten/{plp['Slug']}"
            if plp.get("Slug")
            else None
        ),
        "productId": str(product_id) if product_id not in (None, "") else None,
    }


def extract_pdp_barcode(html_or_json: str | dict | None) -> str | None:
    """Extract GTIN/EAN from PDP HTML, JSON-LD, Next data, or product API JSON."""
    if html_or_json is None:
        return None
    if isinstance(html_or_json, dict):
        barcode = extract_barcode_from_entry(html_or_json)
        if barcode:
            return barcode
        return extract_barcode_from_next_data(html_or_json)
    text = str(html_or_json)
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return extract_pdp_barcode(payload)
    return extract_barcode_from_html(text)


def _fetch_url_text(url: str, *, timeout: int = 30) -> str | None:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": PLUS_USER_AGENT,
            "Accept": "text/html,application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def fetch_plus_product_barcode(
    *,
    link: str | None = None,
    product_id: str | None = None,
) -> str | None:
    """Prefer middleware product API when reachable; otherwise PDP HTML."""
    if product_id:
        body = _fetch_url_text(PLUS_PRODUCT_API.format(product_id=product_id))
        barcode = extract_pdp_barcode(body)
        if barcode:
            return barcode
    if link:
        body = _fetch_url_text(link)
        barcode = extract_pdp_barcode(body)
        if barcode:
            return barcode
    return None


def enrich_plus_entries_with_pdp_barcodes(
    entries: list[dict],
    *,
    limit: int = DEFAULT_PDP_ENRICH_LIMIT,
    workers: int = DEFAULT_PDP_WORKERS,
) -> int:
    """Fill missing barcodes from PDP/detail. Returns number enriched."""
    if limit <= 0:
        return 0

    targets: list[tuple[int, str | None, str | None]] = []
    for index, entry in enumerate(entries):
        if entry.get("barcode"):
            continue
        link = entry.get("link")
        product_id = entry.get("productId")
        if not link and not product_id:
            continue
        targets.append((index, link, product_id))
        if len(targets) >= limit:
            break

    if not targets:
        return 0

    enriched = 0
    workers = max(1, min(workers, 3))

    def _lookup(link: str | None, product_id: str | None) -> str | None:
        try:
            barcode = fetch_plus_product_barcode(link=link, product_id=product_id)
            time.sleep(PDP_ENRICH_DELAY)
            return barcode
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_lookup, link, product_id): index
            for index, link, product_id in targets
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


def _products_from_api_payload(data: dict) -> list[dict[str, str | None]]:
    products: list[dict[str, str | None]] = []
    for row in data.get("ProductList", {}).get("List", []):
        plp = row.get("PLP_Str", row)
        if not isinstance(plp, dict):
            continue
        entry = _product_from_plp(plp)
        if entry["raw_text"]:
            products.append(entry)
    return products


def _product_identity(entry: dict[str, str | None]) -> str:
    link = entry.get("link")
    if link:
        return link
    return entry.get("raw_text") or ""


def _fetch_plp_page(page: Page, url: str, *, dismiss_modals: bool) -> dict:
    """Navigate to a PLP URL and return the parsed API payload."""
    for attempt in range(3):
        try:
            with page.expect_response(
                lambda resp: PLP_API_FRAGMENT in resp.url and resp.status == 200,
                timeout=45000,
            ) as response_info:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                if dismiss_modals or attempt > 0:
                    dismiss_plus_modals(page)
            return response_info.value.json().get("data", {})
        except PlaywrightTimeoutError:
            if attempt < 2:
                dismiss_plus_modals(page)
                continue
    return {}


def _scrape_plp_dom_page(page: Page, category: str, seen: set[str]) -> list[dict]:
    """DOM fallback when the PLP API response is unavailable."""
    products: list[dict] = []
    try:
        page.wait_for_selector(PRODUCT_CARD_SELECTOR, timeout=12000)
    except PlaywrightTimeoutError:
        return products
    cards = page.query_selector_all(PRODUCT_CARD_SELECTOR)
    for card in cards:
        raw_text = card.inner_text().strip()
        if not raw_text:
            continue
        identity = raw_text
        if identity in seen:
            continue
        seen.add(identity)
        img = card.query_selector("img")
        link_el = card.query_selector("a[href*='/producten/']")
        href = link_el.get_attribute("href") if link_el else None
        if href and href.startswith("/"):
            href = f"{PLUS_ORIGIN}{href}"
        products.append(
            {
                "raw_text": raw_text,
                "image": img.get_attribute("src") if img else None,
                "category": category,
                "link": href,
                "barcode": None,
            }
        )
    return products


def scrape_plus_category(
    page: Page,
    url: str,
    *,
    category: str,
    seen: set[str] | None = None,
) -> list[dict]:
    """Scrape a PLUS category by intercepting PLP API responses page-by-page."""
    seen = seen if seen is not None else set()
    products: list[dict] = []
    total_pages = 1

    for page_num in range(1, MAX_API_PAGES + 1):
        page_url = _with_pagina(url, page_num)
        payload = _fetch_plp_page(
            page,
            page_url,
            dismiss_modals=page_num == 1,
        )

        if payload:
            total_pages = max(1, int(payload.get("TotalPages") or 1))
            batch = _products_from_api_payload(payload)
            if not batch:
                batch = _scrape_plp_dom_page(page, category, seen)
        else:
            batch = _scrape_plp_dom_page(page, category, seen)

        new_on_page = 0
        for entry in batch:
            entry = {**entry, "category": category}
            identity = _product_identity(entry)
            if not identity or identity in seen:
                continue
            seen.add(identity)
            products.append(entry)
            new_on_page += 1

        if not batch:
            break
        if page_num >= total_pages:
            break
        if new_on_page == 0 and page_num > 1:
            break

    return products


def scrape_plus_categories(
    page: Page,
    items: list[tuple[str, str]],
    *,
    on_batch: Callable[[list[dict]], None] | None = None,
) -> list[dict]:
    """Scrape multiple (url, category) pairs, optionally persisting after each."""
    all_products: list[dict] = []
    seen: set[str] = set()

    for item_url, category in items:
        batch = scrape_plus_category(page, item_url, category=category, seen=seen)
        all_products.extend(batch)
        if on_batch:
            on_batch(all_products)

    return all_products
