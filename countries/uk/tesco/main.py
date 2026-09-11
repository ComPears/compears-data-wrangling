"""Scrape Tesco UK grocery search results for seed queries."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from uk_scrape import (  # noqa: E402
    StoreSearchConfig, accept_uk_cookies, quote_query, scrape_store_search, search_page_state,
)
from scrape_utils import goto_resilient  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "tesco.json"

def _submit_search(page: Page, query: str) -> None:
    search = page.locator('input[type="search"]').first
    search.fill(query, timeout=15000)
    search.press("Enter")
    page.wait_for_url(
        lambda url: parse_qs(urlsplit(url).query).get("query") == [query],
        timeout=30000,
    )
    # The URL can update before the results. Wait for the new query's heading
    # so previous-query products cannot be mistaken for the requested results.
    heading = re.compile(
        rf'^(?:Results for|Products we[’\']ve found for) [“"]{re.escape(query)}[”"]$',
        re.IGNORECASE,
    )
    page.get_by_role("heading", name=heading).wait_for(state="visible", timeout=30000)


def navigate_tesco_search(page: Page, query: str) -> None:
    """Use the public form, with one homepage recovery for a stalled UI."""
    try:
        _submit_search(page, query)
    except PlaywrightTimeoutError:
        # A long-lived client-side session can stop responding to submissions.
        # Recover its UI once without rotating identities, clearing cookies, or
        # retrying an explicit block page. A second timeout is a real failure.
        if search_page_state(page, None) == "blocked":
            raise
        print("   Recovering stalled Tesco search form through the homepage")
        goto_resilient(page, CFG.warm_url, timeout=45000, retries=1)
        if search_page_state(page, None) == "blocked":
            raise
        page.wait_for_timeout(1500)
        accept_uk_cookies(page)
        page.wait_for_timeout(1500)
        _submit_search(page, query)


CFG = StoreSearchConfig(
    slug="tesco",
    base_url="https://www.tesco.com",
    warm_url="https://www.tesco.com/shop/en-GB/",
    reuse_page=True,
    navigate_search=navigate_tesco_search,
    search_url=lambda q: f"https://www.tesco.com/shop/en-GB/search?query={quote_query(q)}",
    card_selectors=(
        "[data-auto='product-tile']",
        "li[class*='product-list']",
        "div[class*='product-tile']",
        "article",
    ),
)


def main() -> None:
    with sync_playwright() as p:
        scrape_store_search(p, CFG, OUTPUT)


if __name__ == "__main__":
    main()
