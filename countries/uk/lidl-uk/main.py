"""Scrape Lidl UK grocery search results for seed queries."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from uk_scrape import StoreSearchConfig, quote_query, scrape_store_search  # noqa: E402
from lidl_products import extract_lidl_products  # noqa: E402
from seed_queries import SEED_QUERIES  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "lidl_uk.json"

# Lidl's public search mixes groceries with rotating hardware and clothing.
# Keep the 71 shared food searches and use the remaining daily search budget
# for missing grocery departments, rather than non-food search recommendations.
NON_FOOD_QUERIES = {
    "toilet roll", "kitchen roll", "washing up liquid", "laundry detergent",
    "fabric softener", "shampoo", "toothpaste", "deodorant", "bin bags", "nappies",
}
LIDL_QUERIES = [q for q in SEED_QUERIES if q not in NON_FOOD_QUERIES] + [
    "nuts", "figs", "wine", "beer", "cider", "prawns", "pork", "noodles",
    "frozen vegetables",
]

CFG = StoreSearchConfig(
    slug="lidl-uk",
    base_url="https://www.lidl.co.uk",
    warm_url="https://www.lidl.co.uk/",
    extract_products=extract_lidl_products,
    search_url=lambda q: f"https://www.lidl.co.uk/q/search?q={quote_query(q)}",
    card_selectors=(
        "div[data-grid-data]",
        "article.product",
        ".AProductGridItem",
        "li.product",
        "[class*='ProductGrid'] article",
        "[class*='product-grid'] article",
        "article",
    ),
    name_selectors=(
        "[class*='title']",
        "h2",
        "h3",
        "a",
    ),
    price_selectors=(
        "[class*='price']",
        "[data-testid*='price']",
        ".price",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT, queries=LIDL_QUERIES)


if __name__ == "__main__":
    main()
