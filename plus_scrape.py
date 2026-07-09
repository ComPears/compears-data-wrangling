"""Shared PLUS product-list scraper (coop.nl now redirects here)."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from scrape_utils import goto_resilient

PRODUCT_CARD_SELECTOR = ".plp-item-wrapper"
DEFAULT_POSTCODE = "1012AB"


def resolve_redirect_url(url: str, *, timeout: int = 30) -> str:
    """Follow redirects and return the final URL (coop.nl -> plus.nl)."""
    req = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "Mozilla/5.0 (compatible; CompearsBot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl()
    except urllib.error.HTTPError as err:
        if err.headers.get("Location"):
            return err.headers["Location"]
        raise


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
                page.wait_for_timeout(600)
        except Exception:
            pass

    page.evaluate(
        "document.querySelectorAll('[data-popup-backdrop]').forEach(el => el.remove())"
    )
    page.wait_for_timeout(300)

    try:
        page.get_by_role("link", name="Sluit winkel keuze").click(timeout=2000)
        page.wait_for_timeout(400)
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


def _extract_product_count(page: Page) -> int | None:
    try:
        text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        return None
    matches = re.findall(r"(\d+)\s*producten", text, re.IGNORECASE)
    counts = [int(value) for value in matches if int(value) > 0]
    return max(counts) if counts else None


def _card_identity(card) -> str:
    card_id = card.get_attribute("id")
    if card_id:
        return card_id
    title = card.query_selector("h3")
    if title:
        return title.inner_text().strip()
    return card.inner_text().strip()


def scrape_plus_category(
    page: Page,
    url: str,
    *,
    category: str,
    seen: set[str] | None = None,
) -> list[dict]:
    """Scrape all products from a PLUS category URL via ?pagina=N pagination."""
    seen = seen if seen is not None else set()
    products: list[dict] = []
    expected = None
    page_num = 1
    max_pages = 250

    while page_num <= max_pages:
        page_url = _with_pagina(url, page_num)
        goto_resilient(page, page_url, timeout=90000)
        page.wait_for_timeout(1500)
        if page_num == 1:
            dismiss_plus_modals(page)
            expected = _extract_product_count(page)

        try:
            page.wait_for_selector(PRODUCT_CARD_SELECTOR, timeout=15000)
        except PlaywrightTimeoutError:
            if page_num == 1:
                dismiss_plus_modals(page)
                page.wait_for_timeout(1500)
            else:
                break

        cards = page.query_selector_all(PRODUCT_CARD_SELECTOR)
        new_on_page = 0
        for card in cards:
            identity = _card_identity(card)
            raw_text = card.inner_text().strip()
            if not raw_text or identity in seen:
                continue
            seen.add(identity)
            img = card.query_selector("img")
            image_url = img.get_attribute("src") if img else None
            products.append(
                {"raw_text": raw_text, "image": image_url, "category": category}
            )
            new_on_page += 1

        if not cards:
            break
        if new_on_page == 0 and (not expected or len(products) >= expected):
            break
        if expected and len(products) >= expected:
            break
        page_num += 1

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

    for url, category in items:
        batch = scrape_plus_category(page, url, category=category, seen=seen)
        all_products.extend(batch)
        if on_batch:
            on_batch(all_products)

    return all_products
