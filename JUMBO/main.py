import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from category_utils import category_from_url
from jumbo_api_client import (
    fetch_category_products,
    product_to_raw_entry,
    supports_api_scrape,
)
from scrape_utils import (
    accept_common_cookies,
    click_pagination_if_ready,
    configure_page,
    goto_resilient,
    launch_browser,
    report_batch_failures,
    require_products,
    wait_for_products,
)

from links import links


def get_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    last_part = path.rstrip("/").split("/")[-1]
    return last_part or "unknown"


def scrape_with_playwright(link: str) -> list[dict]:
    """Fallback scraper for filter/inspiration URLs that the GraphQL API cannot scope."""
    from playwright.sync_api import sync_playwright

    filename_suffix = get_filename_from_url(link)
    category = category_from_url(link)
    seen: set[str] = set()
    data: list[dict] = []

    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        configure_page(page)

        try:
            goto_resilient(page, link)
            page.wait_for_timeout(3000)
            accept_common_cookies(page)

            while True:
                wait_for_products(page, "article.product-container", timeout=20000)
                cards = page.query_selector_all("article.product-container")
                previous_count = len(seen)

                for card in cards:
                    raw_text = card.inner_text().strip()
                    if raw_text in seen:
                        continue
                    seen.add(raw_text)
                    img = card.query_selector(
                        'div.product-image img[data-testid="jum-product-image"]'
                    )
                    src = img.get_attribute("src") if img else None
                    data.append({"raw_text": raw_text, "image": src, "category": category})

                if len(seen) == previous_count:
                    break
                if not click_pagination_if_ready(
                    page, "button:has-text('Volgende')", label="Jumbo Volgende"
                ):
                    break
                page.wait_for_timeout(1500)
        finally:
            context.close()
            browser.close()

    require_products(len(data), link)
    output_file = f"JSONs/jumbo_products_{filename_suffix}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(data)} products to {output_file} (Playwright)")
    return data


def scrape_with_api(link: str) -> list[dict]:
    category = category_from_url(link)
    api_products = fetch_category_products(link)
    data = [product_to_raw_entry(product) for product in api_products]
    for entry in data:
        entry["category"] = category

    require_products(len(data), link)
    filename_suffix = get_filename_from_url(link)
    output_file = f"JSONs/jumbo_products_{filename_suffix}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(data)} products to {output_file} (API)")
    return data


def scrape_jumbo_products(link_list) -> None:
    os.makedirs("JSONs", exist_ok=True)
    failures: list[tuple[str, str]] = []

    for link in link_list:
        print(f"\n🔄 Scraping: {link}")
        try:
            if supports_api_scrape(link):
                scrape_with_api(link)
            else:
                scrape_with_playwright(link)
        except Exception as err:
            msg = f"{type(err).__name__}: {err}"
            print(f"❌ Failed to scrape {link}: {msg}")
            failures.append((link, msg))

    report_batch_failures(failures, len(link_list))


if __name__ == "__main__":
    scrape_jumbo_products(links)
