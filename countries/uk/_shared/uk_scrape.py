"""Playwright helpers for UK supermarket search scrapes."""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote_plus, urlsplit

from playwright.sync_api import Page, Playwright, Response


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


ROOT = _repo_root()
from scrape_utils import (  # noqa: E402
    configure_page,
    goto_resilient,
    launch_browser,
    write_json_atomic,
)

SHARED_DIR = Path(__file__).resolve().parent
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from seed_queries import SEED_QUERIES  # noqa: E402
from uk_product import parse_gbp_price, raw_product  # noqa: E402


@dataclass(frozen=True)
class StoreSearchConfig:
    slug: str
    base_url: str
    search_url: Callable[[str], str]
    card_selectors: tuple[str, ...]
    name_selectors: tuple[str, ...] = (
        "[data-auto='product-tile'] h3",
        "[data-testid='product-tile-description']",
        "[data-testid='product-title']",
        "h2",
        "h3",
        ".product-title",
        ".co-product__title",
        ".fop-title",
    )
    price_selectors: tuple[str, ...] = (
        "[data-auto='price-value']",
        "[data-testid*='price']",
        "[class*='price']",
        ".price",
        ".co-product__price",
        ".fop-price",
        "[data-test='fop-price']",
    )
    link_selectors: tuple[str, ...] = (
        "a[href*='/products/']",
        "a[href*='/product/']",
        "a[href*='/product']",
        "a[href*='/p/']",
        "a[href*='/groceries/']",
        "a[href]",
    )
    image_selectors: tuple[str, ...] = ("img",)
    size_selectors: tuple[str, ...] = (
        "[data-testid*='size']",
        "[data-test*='size']",
        "[class*='pack-size']",
        "[class*='product-size']",
        "[class*='weight']",
    )
    max_queries: int = 90
    max_per_query: int = 36
    settle_ms: int = 3500
    # Warm homepage before first search (helps Asda/Lidl bot walls).
    warm_url: str | None = None
    # Optional JSON API searched from inside the warmed browser session.
    api_url: Callable[[str], str] | None = None
    # Preserve tab-local session state across searches for session-sensitive stores.
    reuse_page: bool = False
    # Use the retailer's client-side search flow when direct navigation
    # does not preserve the application's search session.
    navigate_search: Callable[[Page, str], None] | None = None
    # Authoritative retailer parser: never fall back to generic price guessing.
    extract_products: Callable[[Page], list[dict[str, Any]]] | None = None


@dataclass(frozen=True)
class ApiHarvestResult:
    products: list[dict[str, Any]]
    status: int | None


def accept_uk_cookies(page: Page) -> None:
    for selector in (
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "button:has-text('Accept')",
        "button:has-text('Allow all')",
        "button:has-text('I accept')",
        "#onetrust-accept-btn-handler",
        "button[id*='accept']",
        "button[data-auto='cookie-accept-all']",
        "#onetrust-accept-btn-handler",
        "button[aria-label*='Accept']",
    ):
        try:
            button = page.locator(selector).first
            if button.count() and button.is_visible(timeout=1500):
                button.click(timeout=3000)
                page.wait_for_timeout(800)
                print(f"🍪 Accepted cookies via {selector}")
                return
        except Exception:
            continue


def _text_or_empty(locator) -> str:
    try:
        if locator.count() == 0:
            return ""
        return (locator.first.inner_text(timeout=1000) or "").strip()
    except Exception:
        return ""


def _attr_or_empty(locator, name: str) -> str:
    try:
        if locator.count() == 0:
            return ""
        return (locator.first.get_attribute(name) or "").strip()
    except Exception:
        return ""


def extract_from_product_links(page: Page, cfg: StoreSearchConfig) -> list[dict[str, Any]]:
    """Pair product links with nearby £x.xx prices (works for Tesco-style grids)."""
    try:
        rows = page.evaluate(
            """(maxCount) => {
              const out = [];
              const seen = new Set();
              const links = [...document.querySelectorAll(
                "a[href*='/products/'], a[href*='/product/'], a[href*='/p/'], a[href*='/groceries/product']"
              )];
              for (const a of links) {
                const href = a.href || '';
                if (!href || seen.has(href)) continue;
                // Skip pure category / navigation links
                if (/\\/(aisles|categories|browse)\\//i.test(href)) continue;
                const name = (a.innerText || '').trim().split('\\n').map(s => s.trim()).find(Boolean) || '';
                if (name.length < 3) continue;
                let el = a;
                let price = '';
                let offer = '';
                let cardText = '';
                for (let i = 0; i < 12 && el; i++) {
                  const text = el.innerText || '';
                  const m = text.match(/£\\s*\\d+(?:[\\.,]\\d{1,2})?|\\b\\d{1,3}\\s*p\\b/i);
                  const offerLine = text.split('\\n').map(s => s.trim()).find(
                    s => /(clubcard|nectar price|aldi price match|special offer|save \\d)/i.test(s)
                  );
                  if (offerLine) offer = offerLine.slice(0, 240);
                  if (m) { price = m[0]; cardText = text; break; }
                  el = el.parentElement;
                }
                if (!price) continue;
                seen.add(href);
                let image = '';
                const img = a.querySelector('img') || (a.parentElement && a.parentElement.querySelector('img'));
                if (img) image = img.src || img.getAttribute('data-src') || img.getAttribute('srcset') || '';
                out.push({ name, price, href, image, offer, cardText });
                if (out.length >= maxCount) break;
              }
              return out;
            }""",
            cfg.max_per_query,
        )
    except Exception:
        return []

    products: list[dict[str, Any]] = []
    for row in rows or []:
        entry = raw_product(
            name=str(row.get("name") or ""),
            price=row.get("price"),
            url=str(row.get("href") or ""),
            image=str(row.get("image") or "") or None,
            size=size_from_text_blob(str(row.get("cardText") or "")),
            offer=str(row.get("offer") or "") or None,
            base_url=cfg.base_url,
            retailer_product_id=(
                str(row.get("href") or "").rstrip("/").split("/")[-1].split("?")[0]
                or None
            ),
        )
        if entry:
            products.append(entry)
    return products


def extract_from_cards(page: Page, cfg: StoreSearchConfig) -> list[dict[str, Any]]:
    linked = extract_from_product_links(page, cfg)
    if linked:
        return linked

    products: list[dict[str, Any]] = []
    cards = None
    for selector in cfg.card_selectors:
        loc = page.locator(selector)
        try:
            if loc.count() > 0:
                cards = loc
                break
        except Exception:
            continue
    if cards is None:
        return products

    count = min(cards.count(), cfg.max_per_query)
    for i in range(count):
        card = cards.nth(i)
        name = ""
        for sel in cfg.name_selectors:
            name = _text_or_empty(card.locator(sel))
            if name:
                break
        if not name:
            name = _text_or_empty(card)
            if name:
                name = name.split("\n")[0].strip()
        price_text = ""
        for sel in cfg.price_selectors:
            price_text = _text_or_empty(card.locator(sel))
            if parse_gbp_price(price_text):
                break
        if not parse_gbp_price(price_text):
            price_text = price_from_text_blob(_text_or_empty(card)) or ""
        href = ""
        for sel in cfg.link_selectors:
            href = _attr_or_empty(card.locator(sel), "href")
            if href:
                break
        image = ""
        for sel in cfg.image_selectors:
            image = _attr_or_empty(card.locator(sel), "src") or _attr_or_empty(
                card.locator(sel), "data-src"
            )
            if image:
                break
        size = ""
        for sel in cfg.size_selectors:
            size = _text_or_empty(card.locator(sel))
            if size:
                break
        if not size:
            size = size_from_text_blob(_text_or_empty(card)) or ""
        entry = raw_product(
            name=name,
            price=price_text,
            url=href,
            image=image,
            size=size,
            base_url=cfg.base_url,
        )
        if entry:
            products.append(entry)
    return products


def extract_json_ld(page: Page, cfg: StoreSearchConfig) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    scripts = page.locator('script[type="application/ld+json"]')
    try:
        total = scripts.count()
    except Exception:
        return products

    for i in range(total):
        try:
            raw = scripts.nth(i).inner_text(timeout=1000)
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            candidates = graph if isinstance(graph, list) else [item]
            for node in candidates:
                if not isinstance(node, dict):
                    continue
                types = node.get("@type")
                type_list = types if isinstance(types, list) else [types]
                if "Product" not in type_list:
                    continue
                offers = node.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price = offers.get("price") if isinstance(offers, dict) else None
                brand_value = node.get("brand")
                if isinstance(brand_value, dict):
                    brand_value = brand_value.get("name")
                entry = raw_product(
                    name=str(node.get("name") or ""),
                    price=price,
                    url=str(node.get("url") or ""),
                    image=str(node.get("image") or "")
                    if not isinstance(node.get("image"), list)
                    else str((node.get("image") or [""])[0]),
                    barcode=str(node.get("gtin13") or node.get("gtin") or "") or None,
                    base_url=cfg.base_url,
                    retailer_product_id=str(node.get("sku") or node.get("productID") or "") or None,
                    availability=str(offers.get("availability") or "") if isinstance(offers, dict) else None,
                    brand=str(brand_value or "") or None,
                    category=str(node.get("category") or "") or None,
                    size=str(
                        node.get("size")
                        or node.get("weight")
                        or node.get("netContent")
                        or ""
                    )
                    or None,
                )
                if entry:
                    products.append(entry)
    return products


def _walk_for_products(obj: Any, found: list[dict[str, Any]], cfg: StoreSearchConfig) -> None:
    if isinstance(obj, dict):
        name = (
            obj.get("title")
            or obj.get("name")
            or obj.get("productName")
            or obj.get("displayName")
        )
        price = None
        price_obj = (
            obj.get("price")
            or obj.get("retail_price")
            or obj.get("retailPrice")
            or obj.get("priceInfo")
            or obj.get("sellingPrice")
        )
        if isinstance(price_obj, dict):
            price = (
                price_obj.get("amountRelevantDisplay")
                or price_obj.get("amountDisplay")
                or price_obj.get("actual")
                or price_obj.get("price")
                or price_obj.get("now")
                or price_obj.get("current")
            )
            if price is None:
                amount = (
                    price_obj.get("amountRelevant")
                    or price_obj.get("amount")
                    or price_obj.get("value")
                )
                # Aldi UK commerce API stores GBP amounts in minor units (pence).
                if (
                    isinstance(amount, int)
                    and amount > 0
                    and str(price_obj.get("currencyCode") or "").upper() == "GBP"
                ):
                    price = amount / 100.0
                else:
                    price = amount
        elif price_obj is not None:
            price = price_obj
        if name and price is not None:
            slug = obj.get("urlSlugText")
            sku = obj.get("sku")
            aldi_path = f"/product/{slug}/{sku}" if slug and sku else ""
            brand_value = obj.get("brand") or obj.get("brandName")
            if isinstance(brand_value, dict):
                brand_value = brand_value.get("name")
            size_value: Any = None
            for key in (
                "sellingSize",
                "size",
                "packageSize",
                "packSize",
                "unitSize",
                "weight",
                "netWeight",
                "volume",
                "netContent",
            ):
                candidate = obj.get(key)
                if candidate not in (None, "", [], {}):
                    size_value = candidate
                    break
            if isinstance(size_value, dict):
                display = (
                    size_value.get("display")
                    or size_value.get("formatted")
                    or size_value.get("text")
                    or size_value.get("label")
                )
                if display:
                    size_value = display
                else:
                    amount = size_value.get("value") or size_value.get("amount")
                    unit = size_value.get("unit") or size_value.get("unitOfMeasure")
                    size_value = f"{amount} {unit}" if amount and unit else None
            entry = raw_product(
                name=str(name),
                price=price,
                url=str(
                    obj.get("url")
                    or obj.get("productUrl")
                    or obj.get("full_url")
                    or obj.get("link")
                    or obj.get("seoURL")
                    or aldi_path
                    or ""
                ),
                image=str(
                    obj.get("defaultImageUrl")
                    or obj.get("image")
                    or obj.get("image_url")
                    or obj.get("imageUrl")
                    or obj.get("imageURL")
                    or ""
                ),
                size=str(size_value or "") or None,
                barcode=str(obj.get("gtin") or obj.get("gtin13") or obj.get("barcode") or "")
                or None,
                base_url=cfg.base_url,
                retailer_product_id=str(
                    obj.get("product_uid") or sku or obj.get("productId") or obj.get("id") or ""
                )
                or None,
                availability=str(obj.get("availability") or obj.get("stockStatus") or "") or None,
                brand=str(brand_value or "") or None,
                category=str(
                    obj.get("categoryName")
                    or obj.get("category")
                    or obj.get("departmentName")
                    or obj.get("department")
                    or ""
                )
                or None,
            )
            if entry:
                # Prefer product_uid URLs for Sainsbury's when missing.
                if not entry.get("i") and obj.get("product_uid"):
                    entry["i"] = (
                        f"{cfg.base_url}/gol-ui/product/{obj.get('product_uid')}"
                    )
                    entry["productUrl"] = entry["i"]
                found.append(entry)
        for value in obj.values():
            _walk_for_products(value, found, cfg)
    elif isinstance(obj, list):
        for item in obj:
            _walk_for_products(item, found, cfg)


def harvest_api_json(page: Page, cfg: StoreSearchConfig, query: str) -> ApiHarvestResult:
    """Fetch a retailer JSON API using the browser's cookies / TLS fingerprint."""
    if not cfg.api_url:
        return ApiHarvestResult([], None)
    api = cfg.api_url(query)
    payload: dict[str, Any] | None = None
    transient_statuses = {0, 429, 500, 502, 503, 504}
    for attempt in range(1, 4):
        try:
            payload = page.evaluate(
                """async (url) => {
                  try {
                    const res = await fetch(url, {
                      credentials: 'include',
                      headers: { 'Accept': 'application/json, text/plain, */*' },
                    });
                    const text = await res.text();
                    return { ok: res.ok, status: res.status, text: text.slice(0, 500000) };
                  } catch (err) {
                    return { ok: false, status: 0, text: String(err) };
                  }
                }""",
                api,
            )
        except Exception as err:
            print(f"   ⚠️ api evaluate failed: {err}")
            payload = {"ok": False, "status": 0, "text": str(err)}

        status = int(payload.get("status") or 0) if payload else 0
        if payload and payload.get("ok"):
            break
        if status not in transient_statuses or attempt == 3:
            break
        delay = (2 ** (attempt - 1)) + random.uniform(0, 0.75)
        print(f"   🔁 transient API HTTP {status}; retry {attempt}/2 in {delay:.1f}s")
        time.sleep(delay)

    if not payload or not payload.get("ok"):
        status = int(payload.get("status") or 0) if payload else 0
        print(f"   ⚠️ api HTTP {status or '?'} for {api[:80]}")
        return ApiHarvestResult([], status)
    try:
        data = json.loads(payload["text"])
    except Exception:
        print("   ⚠️ api JSON parse failed")
        return ApiHarvestResult([], int(payload.get("status") or 200))

    found: list[dict[str, Any]] = []
    # Prefer top-level products arrays when present (Sainsbury's).
    if isinstance(data, dict) and isinstance(data.get("products"), list):
        _walk_for_products(data["products"], found, cfg)
    else:
        _walk_for_products(data, found, cfg)
    return ApiHarvestResult(found[: cfg.max_per_query], int(payload.get("status") or 200))


def attach_json_sniffer(
    page: Page, cfg: StoreSearchConfig, bucket: list[dict[str, Any]]
) -> Callable[[Response], None]:
    def on_response(response: Response) -> None:
        try:
            ctype = (response.headers.get("content-type") or "").lower()
            url = response.url
            url_l = url.lower()
            if response.status != 200:
                return
            if "json" not in ctype and not any(
                token in url_l for token in ("/api/", "search", "product", "graphql", "commerce")
            ):
                return
            data = response.json()
        except Exception:
            return
        found: list[dict[str, Any]] = []
        _walk_for_products(data, found, cfg)
        if not found:
            return
        # Prefer dedicated search endpoints over category trees / analytics.
        priority = 0
        if any(token in url_l for token in ("product-search", "/search", "gol-services/product")):
            priority = 2
        elif "product" in url_l:
            priority = 1
        bucket.append({"priority": priority, "url": url, "products": found})

    page.on("response", on_response)
    return on_response


def search_page_state(page: Page, status: int | None) -> str:
    """Classify failures without persisting potentially sensitive page contents."""
    try:
        content = (page.title() + " " + page.locator("body").inner_text(timeout=2000)).lower()
    except Exception:
        content = ""
    if status in {401, 403, 429} or any(
        marker in content for marker in (
            "access denied", "verify you are human", "unusual traffic", "just a moment",
        )
    ):
        return "blocked"
    if status is not None and status >= 500:
        return "server_error"
    if status is not None and status >= 400:
        return "http_error"
    if any(marker in content for marker in ("no results", "no products found", "couldn't find any")):
        return "no_results"
    return "unclassified_empty"


def same_search_location(actual: str, expected: str) -> bool:
    current, requested = urlsplit(actual), urlsplit(expected)
    current_query, requested_query = parse_qs(current.query), parse_qs(requested.query)
    # Tesco adds inputType when its visible search form is submitted. It is
    # input-method metadata, not a different product query or filter.
    current_query.pop("inputType", None)
    requested_query.pop("inputType", None)
    return (
        current.hostname == requested.hostname
        and current.path == requested.path
        and current_query == requested_query
    )


def write_search_diagnostics(output_file: Path, cfg: StoreSearchConfig, rows: list[dict]) -> None:
    # A separate artifact, never part of a product catalog. No HTML, cookies,
    # headers, response bodies, query strings or exception messages are retained.
    directory = Path(os.environ.get("UK_DIAGNOSTICS_DIR", str(output_file.parent / "diagnostics")))
    write_json_atomic(directory / f"{cfg.slug}-search.json", {
        "store": cfg.slug,
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "queries": rows,
    })


def best_sniffed_products(
    sniffed: list[dict[str, Any]], max_count: int
) -> list[dict[str, Any]]:
    if not sniffed:
        return []
    # Newest highest-priority search payload wins.
    ranked = sorted(
        sniffed,
        key=lambda row: (int(row.get("priority") or 0), sniffed.index(row)),
        reverse=True,
    )
    for row in ranked:
        products = row.get("products") or []
        if products:
            return products[:max_count]
    return []


def dedupe_raw(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = (item.get("i") or item.get("n") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def scrape_store_search(
    playwright: Playwright,
    cfg: StoreSearchConfig,
    output_file: Path,
    *,
    queries: list[str] | None = None,
) -> list[dict[str, Any]]:
    browser = launch_browser(playwright)
    context = browser.new_context(
        locale="en-GB",
        viewport={"width": 1400, "height": 900},
        extra_http_headers={
            "Accept-Language": "en-GB,en;q=0.9",
        },
    )
    # Soften automation fingerprint a bit for UK retailer bot walls.
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    all_products: list[dict[str, Any]] = []
    env_limit = os.environ.get("UK_MAX_QUERIES")
    max_queries = int(env_limit) if env_limit and env_limit.isdigit() else cfg.max_queries
    query_list = (queries or SEED_QUERIES)[: max_queries]
    max_blocked_queries = int(os.environ.get("UK_MAX_BLOCKED_QUERIES", "3"))
    max_empty_queries = int(os.environ.get("UK_MAX_EMPTY_QUERIES", "5"))
    consecutive_blocked = 0
    consecutive_empty = 0
    diagnostics: list[dict] = []
    write_search_diagnostics(output_file, cfg, diagnostics)

    warm = cfg.warm_url or cfg.base_url
    sticky_page: Page | None = None
    warm_page: Page | None = None
    try:
        warm_page = context.new_page()
        if cfg.api_url or cfg.reuse_page:
            sticky_page = warm_page
        # Use the browser's native UA. A frozen Chrome version diverges from
        # Playwright's TLS/client-hints fingerprint and triggers retailer bot walls.
        configure_page(warm_page, user_agent=None)
        goto_resilient(warm_page, warm, timeout=45000, retries=2)
        accept_uk_cookies(warm_page)
        warm_page.wait_for_timeout(1500)
        if cfg.navigate_search:
            # Consent may hydrate after the initial document. Settle it on the
            # homepage: accepting it on a result page can reload that page and
            # turn a successful client-side search into a blocked direct GET.
            accept_uk_cookies(warm_page)
            warm_page.wait_for_timeout(1500)
        print(f"🏠 [{cfg.slug}] warmed {warm}")
        if sticky_page is None:
            warm_page.close()
    except Exception as err:
        print(f"   ⚠️ warm failed: {type(err).__name__}")
        if warm_page is not None and sticky_page is None:
            warm_page.close()

    for query_index, query in enumerate(query_list, start=1):
        url = cfg.search_url(query)
        print(f"\n🔍 [{cfg.slug}] {query} → {url}")
        batch: list[dict[str, Any]] = []
        source_method = ""
        page = sticky_page
        owned_page = False
        if page is None:
            page = context.new_page()
            configure_page(page, user_agent=None)
            owned_page = True
        sniffed: list[dict[str, Any]] = []
        sniffer = attach_json_sniffer(page, cfg, sniffed)
        search_capture = None
        navigation_status: int | None = None
        failed_search_statuses: list[int] = []

        def capture_status(response: Response) -> None:
            nonlocal navigation_status
            try:
                if response.request.is_navigation_request() and response.frame == page.main_frame:
                    navigation_status = response.status
                elif (response.status >= 400
                      and urlsplit(response.url).hostname == urlsplit(cfg.base_url).hostname
                      and any(token in urlsplit(response.url).path.lower() for token in ("search", "graphql", "product"))):
                    failed_search_statuses.append(response.status)
            except Exception:
                pass

        page.on("response", capture_status)
        api_status: int | None = None
        error_type: str | None = None
        error_stage: str | None = None
        try:
            if cfg.api_url:
                api_result = harvest_api_json(page, cfg, query)
                batch = api_result.products
                api_status = api_result.status
                if batch:
                    source_method = "retailer_api"
            if not batch:
                # Capture search JSON while the results page loads (Aldi/Morrisons).
                search_json_holder: list[Any] = []

                def _capture_search(response: Response) -> None:
                    try:
                        u = response.url.lower()
                        if response.status != 200:
                            return
                        if not any(
                            token in u
                            for token in ("product-search", "gol-services/product", "/api/search")
                        ):
                            return
                        search_json_holder.append(response.json())
                    except Exception:
                        return

                page.on("response", _capture_search)
                search_capture = _capture_search
                if cfg.navigate_search:
                    cfg.navigate_search(page, query)
                else:
                    goto_resilient(page, url, timeout=45000, retries=2)
                if not cfg.navigate_search:
                    accept_uk_cookies(page)
                try:
                    page.wait_for_selector(
                        "a[href*='/products/'], a[href*='/product/'], a[href*='/p/'], [class*='product'], [data-auto='product-tile']",
                        timeout=18000,
                    )
                except Exception:
                    page.wait_for_timeout(cfg.settle_ms)
                page.wait_for_timeout(1500)
                for _ in range(3):
                    page.mouse.wheel(0, 2200)
                    page.wait_for_timeout(700)

                # Never use earlier/autocomplete response payloads when the
                # actual search document has since been blocked or redirected.
                if navigation_status is not None and navigation_status >= 400:
                    raise RuntimeError("Search document returned an HTTP error")
                if (cfg.navigate_search or cfg.extract_products) and not same_search_location(page.url, url):
                    raise RuntimeError("Search ended at an unexpected location")

                if cfg.extract_products:
                    batch = cfg.extract_products(page)[: cfg.max_per_query]
                    source_method = "retailer_product_grid"
                elif search_json_holder:
                    found: list[dict[str, Any]] = []
                    _walk_for_products(search_json_holder[-1], found, cfg)
                    if found:
                        batch = found[: cfg.max_per_query]
                        source_method = "captured_search_api"

                if not batch and not cfg.extract_products:
                    batch = extract_from_cards(page, cfg)
                    if batch:
                        source_method = "dom_cards"
                if not batch and not cfg.extract_products:
                    batch = extract_json_ld(page, cfg)
                    if batch:
                        source_method = "json_ld"
                if not batch and not cfg.extract_products:
                    batch = best_sniffed_products(sniffed, cfg.max_per_query)
                    if batch:
                        source_method = "sniffed_api"
                sniffed_batch = best_sniffed_products(sniffed, cfg.max_per_query)
                if not cfg.extract_products and sniffed_batch and (
                    not batch
                    or (
                        any(int(row.get("priority") or 0) >= 2 for row in sniffed)
                        and len(sniffed_batch) >= len(batch)
                    )
                ):
                    batch = sniffed_batch
                    source_method = "sniffed_api"
            for item in batch:
                item.setdefault("sourceQuery", query)
                item.setdefault("sourceUrl", url)
                item.setdefault("sourceMethod", source_method or "unknown")
            before = len(all_products)
            all_products.extend(batch)
            all_products = dedupe_raw(all_products)
            write_json_atomic(output_file, all_products)
            print(f"   +{len(all_products) - before} new (batch {len(batch)}, total {len(all_products)})")

            if batch:
                consecutive_empty = 0
                consecutive_blocked = 0
            else:
                consecutive_empty += 1
        except Exception as err:
            error_type = type(err).__name__
            # Retain only an allowlisted operation, never Playwright's full
            # exception text (which can contain URLs or page content).
            error_stage = next((stage for stage in (
                "Locator.fill", "Locator.press", "Page.wait_for_url", "Locator.wait_for",
            ) if stage in str(err)), None)
            print(f"   ⚠️ query failed: {error_type}")
            consecutive_empty += 1
        finally:
            state = "products" if batch else search_page_state(page, api_status or navigation_status)
            if error_type and not batch and state == "unclassified_empty":
                state = "query_error"
            if not batch and any(status in {401, 403, 429} for status in failed_search_statuses):
                state = "blocked"
            consecutive_blocked = consecutive_blocked + 1 if state == "blocked" else 0
            diagnostics.append({
                "query_index": query_index,
                "navigation_status": navigation_status,
                "api_status": api_status,
                "failed_search_statuses": sorted(set(failed_search_statuses)),
                "state": state,
                "error_type": error_type,
                "error_stage": error_stage,
                "batch_count": len(batch),
                "total_count": len(all_products),
                "source_method": source_method,
                "expected_location": same_search_location(page.url, url),
            })
            write_search_diagnostics(output_file, cfg, diagnostics)
            if not batch:
                print(f"   diagnostic: {state} (HTTP {navigation_status}, API {api_status})")
            page.remove_listener("response", sniffer)
            page.remove_listener("response", capture_status)
            if search_capture is not None:
                page.remove_listener("response", search_capture)
            if owned_page and page is not None:
                page.close()

        if consecutive_blocked >= max_blocked_queries:
            print(
                f"::warning::{cfg.slug} stopped after {consecutive_blocked} consecutive "
                "authorization/bot-wall responses; last-good data will be retained"
            )
            break
        if consecutive_empty >= max_empty_queries:
            print(
                f"::warning::{cfg.slug} stopped after {consecutive_empty} consecutive empty "
                "queries; last-good data will be retained"
            )
            break
        time.sleep(1.2)

    if sticky_page is not None:
        sticky_page.close()

    context.close()
    browser.close()
    final = dedupe_raw(all_products)
    write_json_atomic(output_file, final)
    print(f"✅ [{cfg.slug}] wrote {len(final)} products → {output_file}")
    return final


def quote_query(query: str) -> str:
    return quote_plus(query)


def price_from_text_blob(text: str) -> str | None:
    match = re.search(r"£\s*\d+(?:[.,]\d{1,2})?|\b\d{1,3}\s*p\b", text or "", re.I)
    return parse_gbp_price(match.group(0)) if match else None


_SIZE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b\d{1,3}\s*[x×]\s*\d+(?:[.,]\d+)?\s*"
        r"(?:kg|g|mg|l|litres?|liters?|cl|ml|pints?|fl\s*oz|oz)\b",
        re.I,
    ),
    re.compile(
        r"\b\d+(?:[.,]\d+)?\s*(?:kg|g|mg|l|litres?|liters?|cl|ml|pints?|fl\s*oz|oz)\b",
        re.I,
    ),
    re.compile(
        r"\b\d{1,3}\s*(?:pack|packs|pk|bags?|capsules?|tablets?|rolls?|items?)\b",
        re.I,
    ),
)


def size_from_text_blob(text: str) -> str | None:
    """Extract package evidence from a product card without using unit-price text."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in str(text or "").splitlines()]
    for line in lines or [str(text or "")]:
        if not line or re.search(r"(?:price\s+per|/\s*(?:kg|g|l|ml)|per\s+100)", line, re.I):
            continue
        for pattern in _SIZE_PATTERNS:
            match = pattern.search(line)
            if match:
                return match.group(0).strip()
    return None
