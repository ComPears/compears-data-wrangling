"""Scrape Sainsbury's UK grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from uk_scrape import StoreSearchConfig, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "sainsburys.json"

CFG = StoreSearchConfig(
    slug="sainsburys",
    base_url="https://www.sainsburys.co.uk",
    warm_url="https://www.sainsburys.co.uk/groceries",
    search_url=lambda q: (
        "https://www.sainsburys.co.uk/groceries/search"
        f"?searchTerm={quote_plus(q)}"
    ),
    card_selectors=(
        "[data-testid^='product-tile-']",
        "[id^='product-card-']",
        "li[class*='pt-grid-item']",
        "[data-testid='product-tile']",
        ".pt__row .pt__item",
        "article",
        "li",
    ),
    price_selectors=(
        "[data-testid='pt-retail-price']",
        "[data-testid='contextual-price']",
        "[data-testid*='price']",
        "[class*='price']",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
