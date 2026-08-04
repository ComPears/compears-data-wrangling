"""Scrape Aldi Süd grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from de_scrape import StoreSearchConfig, quote_query, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "aldi_sud.json"

CFG = StoreSearchConfig(
    slug="aldi-sud",
    base_url="https://www.aldi-sued.de",
    warm_url="https://www.aldi-sued.de/",
    search_url=lambda q: (
        f"https://www.aldi-sued.de/suchergebnisse?q={quote_query(q)}"
    ),
    # Walk-in national assortment API (amounts in euro-cents).
    api_url=lambda q: (
        "https://api.aldi-sued.de/v3/product-search?"
        f"currency=EUR&serviceType=walk-in&q={quote_query(q)}"
        "&limit=30&offset=0&sort=relevance&servicePoint=B384"
    ),
    card_selectors=(
        ".product-tile",
        ".product-teaser-item",
        "[class*='product-tile']",
        "[class*='product-grid__item']",
        "article",
    ),
    name_selectors=(
        "[class*='product-tile'] [class*='name']",
        "[class*='title']",
        "h2",
        "h3",
        "a",
    ),
    price_selectors=(
        ".base-price",
        "[class*='base-price']",
        "[class*='price']",
    ),
    link_selectors=(
        "a[href*='/produkt/']",
        "a[href*='/product/']",
        "a[href]",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
