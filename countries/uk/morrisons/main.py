"""Scrape Morrisons UK grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from uk_scrape import StoreSearchConfig, extract_from_cards, quote_query, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "morrisons.json"

CFG = StoreSearchConfig(
    slug="morrisons",
    base_url="https://groceries.morrisons.com",
    search_url=lambda q: f"https://groceries.morrisons.com/search?q={quote_query(q)}",
    card_selectors=(
        "[data-test^='fop-wrapper']",
        ".fop-item",
    ),
    # The generic ancestor text includes unit prices before the selling price.
    price_selectors=("[data-test='fop-price']",),
    name_selectors=("[data-test='fop-title']",),
    link_selectors=("[data-test='fop-product-link']",),
    extract_products=lambda page: extract_from_cards(page, CFG),
    size_selectors=(
        "[data-test='fop-size'] > span:first-child",
        "[data-test='fop-size']",
        ".fop-catch-weight",
        "[data-test*='size']",
        "[class*='pack-size']",
        "[class*='product-size']",
        "[class*='weight']",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
