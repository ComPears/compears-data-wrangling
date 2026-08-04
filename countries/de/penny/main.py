"""Scrape Penny DE weekly-offer search results for seed queries.

Penny.de has no full national product search; offers pages are the public
assortment surface. Seed queries hit `/angebote?search=` and card extractors
prefer Angebotspreis when present.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from de_scrape import StoreSearchConfig, quote_query, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "penny.json"

CFG = StoreSearchConfig(
    slug="penny",
    base_url="https://www.penny.de",
    warm_url="https://www.penny.de/",
    search_url=lambda q: f"https://www.penny.de/angebote?search={quote_query(q)}",
    card_selectors=(
        "a[href*='/angebote/']",
        "article",
        "[class*='tile']",
        "[class*='offer']",
        "[class*='product']",
    ),
    name_selectors=(
        "[class*='title']",
        "h2",
        "h3",
        "a",
    ),
    price_selectors=(
        "[class*='price']",
        "[class*='Price']",
        ".price",
    ),
    link_selectors=(
        "a[href*='/angebote/']",
        "a[href]",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
