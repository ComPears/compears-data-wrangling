"""Fast PLUS product-list scraper via intercepted PLP API responses."""

from __future__ import annotations

import json
from copy import deepcopy
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
from scrape_utils import PLUS_USER_AGENT, launch_browser

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


def scrape_complete_plus_category(
    page: Page,
    url: str,
    *,
    category: str,
    seen: set[str] | None = None,
) -> list[dict]:
    """Fetch every declared page; commit deduplication only after completeness.

    Bootstrap the current public request/version/CSRF token in the browser once,
    then paginate in its cookie-bound API context. No private API credentials or
    hard-coded deployment versions are needed. API response bodies are disposed
    after each request so Playwright does not retain the entire catalog in RAM.
    """
    client = PlusListingClient(page, url)
    first = client.first
    total_pages, total_items = _listing_totals(first)
    products: dict[str, dict] = {}
    for page_num in range(1, total_pages + 1):
        payload = first if page_num == 1 else client.fetch(page_num)
        if _listing_totals(payload) != (total_pages, total_items):
            raise ValueError("PLUS listing totals changed during pagination; retry category")
        rows = payload.get("ProductList", {}).get("List")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"PLUS page {page_num}/{total_pages} has no products")
        batch = _products_from_api_payload(payload)
        if len(batch) != len(rows):
            raise ValueError(f"PLUS page {page_num} contains malformed products")
        before = len(products)
        for entry in batch:
            identity = _product_identity(entry)
            if not identity:
                raise ValueError("PLUS product has no identity")
            products[identity] = {**entry, "category": category}
        if len(products) == before:
            raise ValueError(f"PLUS repeated page {page_num}; refusing truncated catalog")
        if page_num % 25 == 0 or page_num == total_pages:
            print(f"  PLUS page {page_num}/{total_pages}: {len(products)}/{total_items} products", flush=True)
    if len(products) != total_items:
        raise ValueError(f"PLUS category incomplete: {len(products)}/{total_items} unique products")
    seen = seen if seen is not None else set()
    result = [entry for identity, entry in products.items() if identity not in seen]
    seen.update(products)
    return result


def _listing_totals(payload: dict) -> tuple[int, int]:
    try:
        pages = int(payload["TotalPages"])
        items = int(payload["TotalNumberItems"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("PLUS missing pagination totals") from exc
    if not 1 <= pages <= MAX_API_PAGES or items < 1:
        raise ValueError(f"PLUS invalid/unsupported listing totals: {pages} pages, {items} products")
    return pages, items


class PlusListingClient:
    def __init__(self, page: Page, url: str):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "www.plus.nl" or not parsed.path.startswith("/producten/"):
            raise ValueError("PLUS category must use the public HTTPS listing origin")
        slug = parsed.path.rstrip("/").split("/")[-1]

        def matches(response):
            target = urlparse(response.url)
            if target.scheme != "https" or target.netloc != "www.plus.nl" or not target.path.endswith("/" + PLP_API_FRAGMENT):
                return False
            try:
                variables = response.request.post_data_json["screenData"]["variables"]
                return variables["CategorySlug"] == slug and variables["PageNumber"] == 1
            except (KeyError, TypeError, ValueError):
                return False

        with page.expect_response(matches, timeout=45000) as capture:
            page.goto(_with_pagina(url, 1), wait_until="domcontentloaded", timeout=45000)
        response = capture.value
        if response.status != 200:
            raise ValueError(f"PLUS listing bootstrap HTTP {response.status}")
        self.first = response.json().get("data", {})
        _listing_totals(self.first)
        request = response.request
        self.url = request.url
        self.body = request.post_data_json
        self.headers = {key: value for key, value in request.all_headers().items()
                        if key in {"content-type", "x-csrftoken", "outsystems-locale"}}
        self.context = page.context.request
        # Release the heavy storefront document and stop background JS/network.
        page.goto("about:blank", wait_until="commit")

    def fetch(self, page_num: int) -> dict:
        body = deepcopy(self.body)
        variables = body["screenData"]["variables"]
        variables["PageNumber"] = page_num
        variables["URLPageNumber"] = page_num
        for attempt in range(3):
            response = None
            try:
                response = self.context.post(self.url, data=body, headers=self.headers,
                                             timeout=20000, max_redirects=0)
                if response.status in {408, 429, 500, 502, 503, 504}:
                    raise PlaywrightTimeoutError(f"PLUS temporary HTTP {response.status}")
                if response.status != 200:
                    raise ValueError(f"PLUS listing HTTP {response.status}")
                return response.json().get("data", {})
            except PlaywrightTimeoutError:
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))
            finally:
                if response is not None:
                    response.dispose()
        raise RuntimeError("PLUS pagination retries exhausted")


def scrape_plus_category_isolated(playwright, url: str, *, category: str,
                                  seen: set[str], attempts: int = 2) -> list[dict]:
    """A crashed renderer/category never poisons another category or its retry."""
    for attempt in range(attempts):
        browser = None
        try:
            browser = launch_browser(playwright)
            context = browser.new_context(user_agent=PLUS_USER_AGENT, locale="nl-NL")
            context.route("**/*", lambda route: route.abort()
                          if route.request.resource_type in {"image", "media", "font"}
                          else route.continue_())
            batch = scrape_complete_plus_category(context.new_page(), url, category=category, seen=seen)
            return batch
        except Exception as exc:
            if attempt + 1 == attempts:
                raise
            print(f"  PLUS category retry {attempt + 1}/{attempts - 1}: {type(exc).__name__}", flush=True)
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass  # A dead browser must not mask the original failure.
    raise ValueError("PLUS category attempts must be positive")


def scrape_plus_category(
    page: Page,
    url: str,
    *,
    category: str,
    seen: set[str] | None = None,
) -> list[dict]:
    """Legacy browser traversal for COOP redirect compatibility.

    The required PLUS daily catalog uses scrape_complete_plus_category instead.
    COOP can redirect to the generic product index rather than a category URL.
    """
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
