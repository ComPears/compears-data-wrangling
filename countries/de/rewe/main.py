"""Scrape REWE grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from de_scrape import StoreSearchConfig, quote_query, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "rewe.json"

CFG = StoreSearchConfig(
    slug="rewe",
    base_url="https://www.rewe.de",
    warm_url="https://www.rewe.de/",
    search_url=lambda q: (
        f"https://www.rewe.de/shop/productList?search={quote_query(q)}"
    ),
    # Browser-session API (prices often require market/PLZ cookies).
    api_url=lambda q: (
        "https://www.rewe.de/shop/api/products?"
        f"search={quote_query(q)}&objectsPerPage=36"
    ),
    card_selectors=(
        "[class*='search-service-product']",
        "[class*='ProductTile']",
        "[class*='product-tile']",
        "[data-testid*='product']",
        "article",
        "li",
    ),
    name_selectors=(
        "[class*='product-name']",
        "[class*='ProductName']",
        "h2",
        "h3",
        "a",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
