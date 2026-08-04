"""Playwright helpers for DE supermarket search scrapes."""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus

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
    DEFAULT_USER_AGENT,
    configure_page,
    goto_resilient,
    launch_browser,
    write_json_atomic,
)

SHARED_DIR = Path(__file__).resolve().parent
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from de_product import parse_eur_price, raw_product  # noqa: E402
from seed_queries import SEED_QUERIES  # noqa: E402


@dataclass(frozen=True)
class StoreSearchConfig:
    slug: str
    base_url: str
    search_url: Callable[[str], str]
    card_selectors: tuple[str, ...]
    name_selectors: tuple[str, ...] = (
        "[data-testid='product-title']",
        "[class*='title']",
        "h2",
        "h3",
        ".product-title",
        "a.title",
        ".title",
    )
    price_selectors: tuple[str, ...] = (
        "[class*='price']",
        "[data-testid*='price']",
        ".price",
        ".base-price",
        "[class*='Price']",
    )
    link_selectors: tuple[str, ...] = (
        "a[href*='/produkt/']",
        "a[href*='/product/']",
        "a[href*='/products/']",
        "a[href*='/p/']",
        "a[href*='/produkte/']",
        "a[href*='/angebote/']",
        "a[href*='.html']",
        "a[href]",
    )
    image_selectors: tuple[str, ...] = ("img",)
    max_queries: int = 80
    max_per_query: int = 36
    settle_ms: int = 3500
    warm_url: str | None = None
    api_url: Callable[[str], str] | None = None


@dataclass(frozen=True)
class ApiHarvestResult:
    products: list[dict[str, Any]]
    status: int | None


def accept_de_cookies(page: Page) -> None:
    for selector in (
        "button:has-text('Alle akzeptieren')",
        "button:has-text('Alles akzeptieren')",
        "button:has-text('Akzeptieren')",
        "button:has-text('Zustimmen')",
        "button:has-text('Einverstanden')",
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "#onetrust-accept-btn-handler",
        "[data-testid*='uc-accept']",
        "button[id*='accept']",
        "button[aria-label*='Accept']",
        "button[aria-label*='Akzept']",
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


def dismiss_de_overlays(page: Page) -> None:
    """Close zip/market/newsletter overlays when possible; keep national search."""
    for selector in (
        "button:has-text('Schließen')",
        "button:has-text('Abbrechen')",
        "button:has-text('Später')",
        "button:has-text('Nein danke')",
        "button:has-text('Weiter ohne')",
        "button:has-text('Ohne Auswahl')",
        "[aria-label='Schließen']",
        "[aria-label='Close']",
        "button.modal-close",
        "[data-testid*='close']",
    ):
        try:
            button = page.locator(selector).first
            if button.count() and button.is_visible(timeout=800):
                button.click(timeout=2000)
                page.wait_for_timeout(400)
                print(f"🧹 Dismissed overlay via {selector}")
                return
        except Exception:
            continue


def maybe_set_de_zip(page: Page, zip_code: str = "80331") -> None:
    """Best-effort PLZ entry for market-gated shops (Rewe/Penny)."""
    for selector in (
        "input[placeholder*='PLZ']",
        "input[aria-label*='PLZ']",
        "input[id*='zip']",
        "input[name*='zip']",
        "input[name*='postal']",
        "input[id*='postal']",
    ):
        try:
            box = page.locator(selector).first
            if not (box.count() and box.is_visible(timeout=1000)):
                continue
            box.fill(zip_code)
            page.wait_for_timeout(800)
            box.press("Enter")
            page.wait_for_timeout(1200)
            for confirm in (
                "button:has-text('Weiter')",
                "button:has-text('Übernehmen')",
                "button:has-text('Auswählen')",
                "button:has-text('Lieferung')",
                "button:has-text('Markt auswählen')",
                "li[role='option']",
            ):
                try:
                    btn = page.locator(confirm).first
                    if btn.count() and btn.is_visible(timeout=800):
                        btn.click(timeout=2000)
                        page.wait_for_timeout(1500)
                        print(f"📍 Set PLZ {zip_code} via {selector} / {confirm}")
                        return
                except Exception:
                    continue
            print(f"📍 Entered PLZ {zip_code} via {selector}")
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


def _clean_de_name(name: str) -> str:
    text = re.sub(r"\s+", " ", (name or "").strip())
    text = re.sub(
        r"\s+für\s+\d+(?:[.,]\d{1,2})?\s*€?(?:\s*EUR)?\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+\d+[.,]\d{2}\s*€?\s*$", "", text)
    return text.strip(" -–|")


def extract_from_product_links(page: Page, cfg: StoreSearchConfig) -> list[dict[str, Any]]:
    """Pair product links with nearby €x,xx prices."""
    try:
        rows = page.evaluate(
            """(maxCount) => {
              const out = [];
              const seen = new Set();
              const links = [...document.querySelectorAll(
                "a[href*='/produkt/'], a[href*='/product/'], a[href*='/produkte/'], a[href*='/p/'], a[href*='/angebote/'], a[href*='.html']"
              )];
              const priceIn = (el) => {
                if (!el) return '';
                // Prefer dedicated price nodes over large ancestor text blobs.
                // Lidl often renders "19.99*" without a € glyph in the price node.
                const nodes = el.querySelectorAll
                  ? el.querySelectorAll("[class*='price'], [class*='Price'], .base-price, [data-testid*='price'], .ods-price__value")
                  : [];
                for (const node of nodes) {
                  const t = (node.innerText || '').replace(/\\u00a0/g, ' ').trim();
                  const offer = t.match(/Angebotspreis\\s*(\\d+[.,]\\d{2})\\s*€?/i);
                  const m = offer
                    || t.match(/(\\d+[.,]\\d{2})\\s*€/)
                    || t.match(/€\\s*(\\d+[.,]\\d{2})/)
                    || t.match(/^(\\d+[.,]\\d{2})\\*?$/);
                  if (m) return (m[1] || m[0]);
                }
                const text = (el.innerText || '').replace(/\\u00a0/g, ' ');
                // Keep this scoped: only accept "für X EUR" on the link itself / small nodes.
                if (text.length < 160) {
                  const fuer = text.match(/für\\s+(\\d+[.,]\\d{2})\\s*€?(?:\\s*EUR)?/i);
                  if (fuer) return fuer[1];
                  const euro = text.match(/(\\d+[.,]\\d{2})\\s*€/);
                  if (euro) return euro[1];
                }
                return '';
              };
              for (const a of links) {
                const href = a.href || '';
                if (!href || seen.has(href)) continue;
                if (/(kategorie|category|marktsuche|filiale|login|warenkorb|cart|fragment)/i.test(href)) continue;
                // Lidl product detail links look like /p/.../p123
                if (href.includes('/p/') && !/\\/p\\d+/i.test(href) && !href.includes('/produkt/')) {
                  // keep generic /p/slug/pID style only
                }
                seen.add(href);
                let name = (a.getAttribute('title') || a.getAttribute('aria-label') || '').trim();
                if (!name) {
                  name = (a.innerText || '').trim().split('\\n').map(s => s.trim()).find(Boolean) || '';
                }
                name = name.replace(/\\s+für\\s+\\d+(?:[.,]\\d{1,2})?\\s*€?(?:\\s*EUR)?\\s*$/i, '').trim();
                if (name.length < 3) continue;
                if (/^(produkte|angebote|top angebote|sortiment)$/i.test(name)) continue;
                let el = a;
                let price = '';
                for (let i = 0; i < 6 && el; i++) {
                  price = priceIn(el);
                  if (price) break;
                  el = el.parentElement;
                }
                if (!price) continue;
                let image = '';
                const img = a.querySelector('img') || (a.parentElement && a.parentElement.querySelector('img'));
                if (img) image = img.src || img.getAttribute('data-src') || img.getAttribute('srcset') || '';
                out.push({ name, price, href, image });
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
            name=_clean_de_name(str(row.get("name") or "")),
            price=row.get("price"),
            url=str(row.get("href") or ""),
            image=str(row.get("image") or "") or None,
            base_url=cfg.base_url,
        )
        if entry:
            products.append(entry)
    return products


def _prices_look_collapsed(products: list[dict[str, Any]]) -> bool:
    """True when many rows share one identical price (shared ancestor bleed)."""
    if len(products) < 6:
        return False
    prices = [str(p.get("p") or "") for p in products if p.get("p")]
    if not prices:
        return False
    dominant = max(prices.count(x) for x in set(prices))
    return dominant / len(prices) >= 0.8


def extract_from_cards(page: Page, cfg: StoreSearchConfig) -> list[dict[str, Any]]:
    linked = extract_from_product_links(page, cfg)
    if linked and not _prices_look_collapsed(linked):
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
                # Prefer a non-price, non-nav line.
                for line in name.split("\n"):
                    line = line.strip()
                    if len(line) < 3:
                        continue
                    if re.search(r"€|Angebotspreis|Streichpreis|UVP|App-preis", line, re.I):
                        continue
                    name = line
                    break
        price_text = ""
        for sel in cfg.price_selectors:
            price_text = _text_or_empty(card.locator(sel))
            if parse_eur_price(price_text):
                break
        if not parse_eur_price(price_text):
            blob = _text_or_empty(card)
            offer = re.search(r"Angebotspreis\s*(\d+[.,]\d{2})\s*€?", blob or "", re.I)
            price_text = (
                offer.group(1) if offer else (price_from_text_blob(blob) or "")
            )
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
        entry = raw_product(
            name=_clean_de_name(name),
            price=price_text,
            url=href,
            image=image,
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
                entry = raw_product(
                    name=str(node.get("name") or ""),
                    price=price,
                    url=str(node.get("url") or ""),
                    image=str(node.get("image") or "")
                    if not isinstance(node.get("image"), list)
                    else str((node.get("image") or [""])[0]),
                    barcode=str(node.get("gtin13") or node.get("gtin") or "") or None,
                    base_url=cfg.base_url,
                )
                if entry:
                    products.append(entry)
    return products


def _rewe_article_price(article: dict[str, Any]) -> Any:
    for key in (
        "price",
        "listingPrice",
        "orderPrice",
        "currentPrice",
        "grossPrice",
        "retailPrice",
    ):
        val = article.get(key)
        if val is None:
            continue
        if isinstance(val, dict):
            return (
                val.get("value")
                or val.get("amount")
                or val.get("price")
                or val.get("gross")
                or val
            )
        return val
    return None


def _walk_for_products(obj: Any, found: list[dict[str, Any]], cfg: StoreSearchConfig) -> None:
    if isinstance(obj, dict):
        # Rewe nests sellable rows under _embedded.articles.
        articles = None
        embedded = obj.get("_embedded")
        if isinstance(embedded, dict) and isinstance(embedded.get("articles"), list):
            articles = embedded["articles"]

        name = (
            obj.get("title")
            or obj.get("name")
            or obj.get("productName")
            or obj.get("displayName")
            or obj.get("brandName")
        )
        # Prefer brand + name for Aldi-style tiles.
        if obj.get("brandName") and obj.get("name"):
            name = f"{obj.get('brandName')} {obj.get('name')}"

        price = None
        if articles:
            for article in articles:
                if isinstance(article, dict):
                    price = _rewe_article_price(article)
                    if price is not None:
                        break
        if price is None:
            price_obj = (
                obj.get("price")
                or obj.get("retail_price")
                or obj.get("retailPrice")
                or obj.get("priceInfo")
                or obj.get("pricePerUnit")
                or obj.get("sellingPrice")
                or obj.get("listingPrice")
            )
            if isinstance(price_obj, dict):
                price = (
                    price_obj.get("amountRelevantDisplay")
                    or price_obj.get("amountDisplay")
                    or price_obj.get("actual")
                    or price_obj.get("price")
                    or price_obj.get("now")
                    or price_obj.get("current")
                    or price_obj.get("value")
                )
                if price is None:
                    amount = (
                        price_obj.get("amountRelevant")
                        or price_obj.get("amount")
                        or price_obj.get("value")
                    )
                    currency = str(price_obj.get("currencyCode") or "").upper()
                    if (
                        isinstance(amount, int)
                        and amount > 0
                        and currency in {"EUR", "GBP", ""}
                    ):
                        # Aldi / Lidl commerce APIs store amounts in minor units.
                        price = amount / 100.0
                    else:
                        price = amount
            elif price_obj is not None:
                price = price_obj

        if name and price is not None:
            slug = obj.get("urlSlugText")
            sku = obj.get("sku")
            aldi_path = f"/produkt/{slug}-{sku}" if slug and sku else ""
            nan = obj.get("nan") or obj.get("id")
            rewe_path = f"/produkte/{nan}" if nan and cfg.slug == "rewe" else ""
            image = ""
            media = obj.get("media")
            if isinstance(media, dict):
                images = media.get("images") or []
                if images and isinstance(images[0], dict):
                    links = (images[0].get("_links") or {}).get("self") or {}
                    image = str(links.get("href") or "")
            if not image:
                image = str(
                    obj.get("defaultImageUrl")
                    or obj.get("image")
                    or obj.get("image_url")
                    or obj.get("imageUrl")
                    or obj.get("imageURL")
                    or ""
                )
            links = obj.get("_links") or {}
            self_link = ""
            if isinstance(links, dict):
                self_obj = links.get("self") or links.get("product") or {}
                if isinstance(self_obj, dict):
                    self_link = str(self_obj.get("href") or "")
            entry = raw_product(
                name=str(name),
                price=price,
                url=str(
                    obj.get("url")
                    or obj.get("productUrl")
                    or obj.get("full_url")
                    or obj.get("link")
                    or obj.get("seoURL")
                    or self_link
                    or aldi_path
                    or rewe_path
                    or ""
                ),
                image=image or None,
                size=str(obj.get("sellingSize") or obj.get("size") or "") or None,
                barcode=str(obj.get("gtin") or obj.get("gtin13") or obj.get("barcode") or "")
                or None,
                base_url=cfg.base_url,
            )
            if entry:
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
    # Prefer known product arrays when present.
    if isinstance(data, dict):
        embedded = data.get("_embedded")
        if isinstance(embedded, dict) and isinstance(embedded.get("products"), list):
            _walk_for_products(embedded["products"], found, cfg)
        elif isinstance(data.get("products"), list):
            _walk_for_products(data["products"], found, cfg)
        elif isinstance(data.get("data"), list):
            _walk_for_products(data["data"], found, cfg)
        else:
            _walk_for_products(data, found, cfg)
    else:
        _walk_for_products(data, found, cfg)
    return ApiHarvestResult(found[: cfg.max_per_query], int(payload.get("status") or 200))


def attach_json_sniffer(page: Page, cfg: StoreSearchConfig, bucket: list[dict[str, Any]]) -> None:
    def on_response(response: Response) -> None:
        try:
            ctype = (response.headers.get("content-type") or "").lower()
            url = response.url
            url_l = url.lower()
            if response.status != 200:
                return
            if "json" not in ctype and not any(
                token in url_l
                for token in ("/api/", "search", "product", "graphql", "commerce")
            ):
                return
            data = response.json()
        except Exception:
            return
        found: list[dict[str, Any]] = []
        _walk_for_products(data, found, cfg)
        if not found:
            return
        priority = 0
        if any(
            token in url_l
            for token in ("product-search", "/search", "api/products", "productlist")
        ):
            priority = 2
        elif "product" in url_l:
            priority = 1
        bucket.append({"priority": priority, "url": url, "products": found})

    page.on("response", on_response)


def best_sniffed_products(
    sniffed: list[dict[str, Any]], max_count: int
) -> list[dict[str, Any]]:
    if not sniffed:
        return []
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
        user_agent=DEFAULT_USER_AGENT,
        locale="de-DE",
        viewport={"width": 1400, "height": 900},
        extra_http_headers={
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        },
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    all_products: list[dict[str, Any]] = []
    env_limit = os.environ.get("DE_MAX_QUERIES")
    max_queries = int(env_limit) if env_limit and env_limit.isdigit() else cfg.max_queries
    query_list = (queries or SEED_QUERIES)[:max_queries]
    max_blocked_queries = int(os.environ.get("DE_MAX_BLOCKED_QUERIES", "3"))
    max_empty_queries = int(os.environ.get("DE_MAX_EMPTY_QUERIES", "5"))
    consecutive_blocked = 0
    consecutive_empty = 0

    warm = cfg.warm_url or cfg.base_url
    sticky_page: Page | None = None
    try:
        warm_page = context.new_page()
        configure_page(warm_page)
        goto_resilient(warm_page, warm, timeout=45000, retries=2)
        accept_de_cookies(warm_page)
        dismiss_de_overlays(warm_page)
        maybe_set_de_zip(warm_page)
        warm_page.wait_for_timeout(1500)
        print(f"🏠 [{cfg.slug}] warmed {warm}")
        if cfg.api_url:
            sticky_page = warm_page
        else:
            warm_page.close()
    except Exception as err:
        print(f"   ⚠️ warm failed: {type(err).__name__}: {err}")

    for query in query_list:
        url = cfg.search_url(query)
        print(f"\n🔍 [{cfg.slug}] {query} → {url}")
        batch: list[dict[str, Any]] = []
        page = sticky_page
        owned_page = False
        if page is None:
            page = context.new_page()
            configure_page(page)
            owned_page = True
        sniffed: list[dict[str, Any]] = []
        attach_json_sniffer(page, cfg, sniffed)
        api_status: int | None = None
        try:
            if cfg.api_url:
                api_result = harvest_api_json(page, cfg, query)
                batch = api_result.products
                api_status = api_result.status
            if not batch:
                search_json_holder: list[Any] = []

                def _capture_search(response: Response) -> None:
                    try:
                        u = response.url.lower()
                        if response.status != 200:
                            return
                        if not any(
                            token in u
                            for token in (
                                "product-search",
                                "/api/products",
                                "/api/search",
                                "productlist",
                            )
                        ):
                            return
                        search_json_holder.append(response.json())
                    except Exception:
                        return

                page.on("response", _capture_search)
                goto_resilient(page, url, timeout=45000, retries=2)
                accept_de_cookies(page)
                dismiss_de_overlays(page)
                maybe_set_de_zip(page)
                try:
                    page.wait_for_selector(
                        "a[href*='/produkt/'], a[href*='/product/'], a[href*='/p/'], "
                        "a[href*='/angebote/'], [class*='product'], .product-item, "
                        "[data-testselector*='product']",
                        timeout=18000,
                    )
                except Exception:
                    page.wait_for_timeout(cfg.settle_ms)
                page.wait_for_timeout(1500)
                for _ in range(3):
                    page.mouse.wheel(0, 2200)
                    page.wait_for_timeout(700)

                if search_json_holder:
                    found: list[dict[str, Any]] = []
                    _walk_for_products(search_json_holder[-1], found, cfg)
                    if found:
                        batch = found[: cfg.max_per_query]

                if not batch:
                    batch = extract_from_cards(page, cfg)
                if not batch:
                    batch = extract_json_ld(page, cfg)
                if not batch:
                    batch = best_sniffed_products(sniffed, cfg.max_per_query)
                sniffed_batch = best_sniffed_products(sniffed, cfg.max_per_query)
                if sniffed_batch and (
                    not batch
                    or (
                        any(int(row.get("priority") or 0) >= 2 for row in sniffed)
                        and len(sniffed_batch) >= len(batch)
                    )
                ):
                    batch = sniffed_batch
            before = len(all_products)
            all_products.extend(batch)
            all_products = dedupe_raw(all_products)
            write_json_atomic(output_file, all_products)
            print(
                f"   +{len(all_products) - before} new "
                f"(batch {len(batch)}, total {len(all_products)})"
            )

            if batch:
                consecutive_empty = 0
                consecutive_blocked = 0
            else:
                consecutive_empty += 1
                consecutive_blocked = (
                    consecutive_blocked + 1 if api_status in {401, 403} else 0
                )
        except Exception as err:
            print(f"   ⚠️ query failed: {type(err).__name__}: {err}")
            consecutive_empty += 1
        finally:
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
    cleaned = (text or "").replace("\xa0", " ")
    # Prefer explicit euro / "für X EUR" / trailing starred amounts (Lidl).
    for pattern in (
        r"Angebotspreis\s*(\d+[.,]\d{2})\s*€?",
        r"für\s+(\d+[.,]\d{2})\s*€?(?:\s*EUR)?",
        r"(\d+[.,]\d{2})\s*€",
        r"€\s*(\d+[.,]\d{2})",
        r"\b(\d+[.,]\d{2})\*?\b",
    ):
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            return parse_eur_price(match.group(1))
    return None
