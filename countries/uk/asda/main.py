"""Scrape Asda UK grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from uk_scrape import StoreSearchConfig, quote_query, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "asda.json"

CFG = StoreSearchConfig(
    slug="asda",
    base_url="https://groceries.asda.com",
    search_url=lambda q: f"https://groceries.asda.com/search/{quote_query(q)}",
    card_selectors=(
        "li.co-item",
        ".co-product",
        "[data-testid='product-tile']",
        "article",
        "li",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
