"""Scrape Lidl UK grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from uk_scrape import StoreSearchConfig, quote_query, scrape_store_search  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "lidl_uk.json"

CFG = StoreSearchConfig(
    slug="lidl-uk",
    base_url="https://www.lidl.co.uk",
    search_url=lambda q: f"https://www.lidl.co.uk/q/search?q={quote_query(q)}",
    card_selectors=(
        "div[data-grid-data]",
        "article.product",
        ".AProductGridItem",
        "li.product",
        "article",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
