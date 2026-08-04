"""Scrape Edeka (EDEKA24) grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from de_scrape import StoreSearchConfig, quote_query, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "edeka.json"

CFG = StoreSearchConfig(
    slug="edeka",
    base_url="https://www.edeka24.de",
    warm_url="https://www.edeka24.de/",
    # OXID eShop search (edeka.de itself is market/offers-only).
    search_url=lambda q: (
        f"https://www.edeka24.de/index.php?cl=search&searchparam={quote_query(q)}"
    ),
    card_selectors=(
        ".product-item",
        ".product-list .product-item",
        "li.product-item",
        "[class*='product-item']",
        "article",
    ),
    name_selectors=(
        "a.title h2",
        "a.title",
        "h2",
        "h3",
        ".title",
    ),
    price_selectors=(
        ".price",
        "[class*='price']",
        ".product-price",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
