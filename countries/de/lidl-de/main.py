"""Scrape Lidl DE grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from de_scrape import StoreSearchConfig, quote_query, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "lidl_de.json"

CFG = StoreSearchConfig(
    slug="lidl-de",
    base_url="https://www.lidl.de",
    warm_url="https://www.lidl.de/",
    search_url=lambda q: f"https://www.lidl.de/q/search?q={quote_query(q)}",
    card_selectors=(
        "[data-testselector='s-product-grid__list-item']",
        ".odsc-tile",
        "[class*='product-grid'] article",
        "article.product",
        "li.product",
        "article",
    ),
    name_selectors=(
        ".product-grid-box__title",
        "[class*='product-grid-box__title']",
        "[class*='title']",
        "h2",
        "h3",
        "a",
    ),
    price_selectors=(
        ".ods-price__value",
        ".product-grid-box__price",
        ".price-wrapper",
        "[class*='ods-price']",
        "[class*='price']",
        "[data-testid*='price']",
        ".price",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
