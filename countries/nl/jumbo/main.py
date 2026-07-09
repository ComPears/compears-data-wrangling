import json
import sys
from pathlib import Path
from urllib.parse import urlparse

def _repo_root():
    from pathlib import Path
    import sys
    p = Path(__file__).resolve().parent
    for _ in range(8):
        if (p / "config" / "stores.json").is_file():
            s = str(p)
            if s not in sys.path:
                sys.path.insert(0, s)
            return p
        p = p.parent
    raise RuntimeError("Could not find compears-data-wrangling root")

_repo_root()
from category_utils import category_from_url
from jumbo_api_client import (
    JumboApiScopeError,
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
    write_json_atomic,
)

from links import links

JSONS_DIR = Path(__file__).resolve().parent / "JSONs"


def get_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    last_part = path.rstrip("/").split("/")[-1]
    return last_part or "unknown"


def category_output_path(link: str) -> Path:
    return JSONS_DIR / f"jumbo_products_{get_filename_from_url(link)}.json"


def scrape_with_playwright(link: str) -> list[dict]:
    """Fallback scraper for filter/inspiration URLs that the GraphQL API cannot scope."""
    from playwright.sync_api import sync_playwright

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
    output_file = category_output_path(link)
    write_json_atomic(output_file, data)
    print(f"✅ Saved {len(data)} products to {output_file} (Playwright)")
    return data


def scrape_with_api(link: str) -> list[dict]:
    category = category_from_url(link)
    api_products = fetch_category_products(link)
    data = [product_to_raw_entry(product) for product in api_products]
    for entry in data:
        entry["category"] = category

    require_products(len(data), link)
    output_file = category_output_path(link)
    write_json_atomic(output_file, data)
    print(f"✅ Saved {len(data)} products to {output_file} (API)")
    return data


def scrape_jumbo_products(link_list) -> None:
    JSONS_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[tuple[str, str]] = []

    for link in link_list:
        print(f"\n🔄 Scraping: {link}")
        output_file = category_output_path(link)
        if output_file.exists():
            output_file.unlink()
        try:
            if supports_api_scrape(link):
                try:
                    scrape_with_api(link)
                except JumboApiScopeError as err:
                    print(f"⚠️ API scope too broad, falling back to Playwright: {err}")
                    scrape_with_playwright(link)
            else:
                scrape_with_playwright(link)
        except Exception as err:
            msg = f"{type(err).__name__}: {err}"
            print(f"❌ Failed to scrape {link}: {msg}")
            failures.append((link, msg))

    report_batch_failures(failures, len(link_list))


if __name__ == "__main__":
    scrape_jumbo_products(links)
