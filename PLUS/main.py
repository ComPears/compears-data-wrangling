import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from category_utils import category_from_url
from plus_scrape import scrape_plus_category
from scrape_utils import (
    PLUS_USER_AGENT,
    configure_page,
    launch_browser,
    report_batch_failures,
    require_products,
    write_json_atomic,
)

OUTPUT_FILE = Path(__file__).resolve().parent / "plus.json"


def scrape_plus_products(links: list[str], output_file: Path = OUTPUT_FILE) -> None:
    product_data: list[dict] = []
    seen: set[str] = set()
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context(
            user_agent=PLUS_USER_AGENT,
            locale="nl-NL",
        )
        page = context.new_page()
        configure_page(page, width=1280, height=800)

        for url in links:
            print(f"\n🌐 Scraping: {url}")
            try:
                category = category_from_url(url)
                batch = scrape_plus_category(
                    page, url, category=category, seen=seen
                )
                require_products(len(batch), url)
                product_data.extend(batch)
                write_json_atomic(output_file, product_data)
                print(
                    f"🗂️ Scraped {len(batch)} products from {url}. "
                    f"Total: {len(product_data)}"
                )
            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {url}: {msg}")
                failures.append((url, msg))

        context.close()
        browser.close()
        print("🎯 Done.")

    report_batch_failures(failures, len(links))


if __name__ == "__main__":
    from links import links

    scrape_plus_products(links)
