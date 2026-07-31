"""Scrape Sainsbury's UK grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from uk_scrape import StoreSearchConfig, quote_query, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "sainsburys.json"

CFG = StoreSearchConfig(
    slug="sainsburys",
    base_url="https://www.sainsburys.co.uk",
    search_url=lambda q: f"https://www.sainsburys.co.uk/gol-ui/SearchResults/{quote_query(q)}",
    card_selectors=(
        "li[class*='pt-grid-item']",
        "[data-testid='product-tile']",
        ".pt__row .pt__item",
        "article",
        "li",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
