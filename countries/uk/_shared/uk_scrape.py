"""Playwright helpers for UK supermarket search scrapes."""

from __future__ import annotations

import json
import os
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
        "h2",
        "h3",
        ".product-title",
        ".co-product__title",
        "a[href*='/product']",
        "a[href*='/products/']",
    )
    price_selectors: tuple[str, ...] = (
        "[data-auto='price-value']",
        "[class*='price']",
        "[data-testid*='price']",
        ".price",
        ".co-product__price",
    )
    link_selectors: tuple[str, ...] = (
        "a[href*='/products/']",
        "a[href*='/product/']",
        "a[href*='/product']",
        "a[href]",
    )
    image_selectors: tuple[str, ...] = ("img",)
    max_queries: int = 40
    max_per_query: int = 24
    settle_ms: int = 2500


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
              const links = [...document.querySelectorAll("a[href*='/products/'], a[href*='/product/']")];
              for (const a of links) {
                const href = a.href || '';
                if (!href || seen.has(href)) continue;
                seen.add(href);
                const name = (a.innerText || '').trim().split('\\n').map(s => s.trim()).find(Boolean) || '';
                if (name.length < 3) continue;
                let el = a;
                let price = '';
                for (let i = 0; i < 10 && el; i++) {
                  const text = el.innerText || '';
                  const m = text.match(/£\\s*\\d+\\.\\d{2}/);
                  if (m) { price = m[0]; break; }
                  el = el.parentElement;
                }
                if (!price) continue;
                let image = '';
                const img = a.querySelector('img') || (a.parentElement && a.parentElement.querySelector('img'));
                if (img) image = img.src || img.getAttribute('data-src') || '';
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
            name=str(row.get("name") or ""),
            price=row.get("price"),
            url=str(row.get("href") or ""),
            image=str(row.get("image") or "") or None,
            base_url=cfg.base_url,
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
        price_text = ""
        for sel in cfg.price_selectors:
            price_text = _text_or_empty(card.locator(sel))
            if parse_gbp_price(price_text):
                break
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
            name=name,
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


def _walk_for_products(obj: Any, found: list[dict[str, Any]], cfg: StoreSearchConfig) -> None:
    if isinstance(obj, dict):
        name = obj.get("title") or obj.get("name") or obj.get("productName")
        price = None
        price_obj = obj.get("price") or obj.get("retailPrice") or obj.get("priceInfo")
        if isinstance(price_obj, dict):
            price = (
                price_obj.get("actual")
                or price_obj.get("price")
                or price_obj.get("amount")
                or price_obj.get("value")
            )
        elif price_obj is not None:
            price = price_obj
        if name and price is not None:
            entry = raw_product(
                name=str(name),
                price=price,
                url=str(obj.get("url") or obj.get("productUrl") or obj.get("link") or ""),
                image=str(
                    obj.get("defaultImageUrl")
                    or obj.get("image")
                    or obj.get("imageUrl")
                    or ""
                ),
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


def attach_json_sniffer(page: Page, cfg: StoreSearchConfig, bucket: list[dict[str, Any]]) -> None:
    def on_response(response: Response) -> None:
        try:
            ctype = (response.headers.get("content-type") or "").lower()
            if "json" not in ctype:
                return
            if response.status != 200:
                return
            data = response.json()
        except Exception:
            return
        found: list[dict[str, Any]] = []
        _walk_for_products(data, found, cfg)
        bucket.extend(found)

    page.on("response", on_response)


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
        locale="en-GB",
        viewport={"width": 1400, "height": 900},
    )
    all_products: list[dict[str, Any]] = []
    env_limit = os.environ.get("UK_MAX_QUERIES")
    max_queries = int(env_limit) if env_limit and env_limit.isdigit() else cfg.max_queries
    query_list = (queries or SEED_QUERIES)[: max_queries]

    for query in query_list:
        url = cfg.search_url(query)
        print(f"\n🔍 [{cfg.slug}] {query} → {url}")
        page = context.new_page()
        configure_page(page)
        sniffed: list[dict[str, Any]] = []
        attach_json_sniffer(page, cfg, sniffed)
        try:
            goto_resilient(page, url, timeout=45000, retries=2)
            accept_uk_cookies(page)
            try:
                page.wait_for_selector("a[href*='/products/'], a[href*='/product/']", timeout=15000)
            except Exception:
                page.wait_for_timeout(cfg.settle_ms)
            page.wait_for_timeout(1200)
            # Nudge lazy loaders
            page.mouse.wheel(0, 2400)
            page.wait_for_timeout(800)

            batch = extract_from_cards(page, cfg)
            if not batch:
                batch = extract_json_ld(page, cfg)
            if not batch:
                # Use recently sniffed network products for this page.
                batch = sniffed[-cfg.max_per_query :]
            before = len(all_products)
            all_products.extend(batch)
            all_products = dedupe_raw(all_products)
            write_json_atomic(output_file, all_products)
            print(f"   +{len(all_products) - before} new (batch {len(batch)}, total {len(all_products)})")
        except Exception as err:
            print(f"   ⚠️ query failed: {type(err).__name__}: {err}")
        finally:
            page.close()
        time.sleep(2.0)

    context.close()
    browser.close()
    final = dedupe_raw(all_products)
    write_json_atomic(output_file, final)
    print(f"✅ [{cfg.slug}] wrote {len(final)} products → {output_file}")
    return final


def quote_query(query: str) -> str:
    return quote_plus(query)


def price_from_text_blob(text: str) -> str | None:
    match = re.search(r"£\s*\d+(?:\.\d{1,2})?", text or "")
    return parse_gbp_price(match.group(0)) if match else None
