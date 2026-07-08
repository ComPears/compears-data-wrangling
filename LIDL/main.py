import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from links import links

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from category_utils import category_from_url
from scrape_utils import (
    accept_common_cookies,
    configure_page,
    goto_resilient,
    launch_browser,
    report_batch_failures,
    require_products,
    wait_for_products,
)


def scrape_lidl_pages() -> None:
    all_data: list[dict] = []
    seen: set[str] = set()
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = launch_browser(p)

        for url in links:
            print(f"🌐 Scraping: {url}")
            context = browser.new_context()
            page = context.new_page()
            configure_page(page)

            try:
                goto_resilient(page, url)
                page.wait_for_timeout(2000)
                accept_common_cookies(page)

                print("🔄 Scrolling to load all products...")
                for _ in range(30):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(400)

                wait_for_products(page, "div.odsc-tile", timeout=20000)
                category = category_from_url(url)
                cards = page.query_selector_all("div.odsc-tile")
                print(f"📦 Found {len(cards)} product cards.")

                url_count = 0
                for card in cards:
                    text = card.inner_text().strip()
                    if text in seen:
                        continue
                    seen.add(text)
                    img = card.query_selector("img.odsc-image-gallery__image")
                    src = img.get_attribute("src") if img else None
                    all_data.append({"raw_text": text, "image": src, "category": category})
                    url_count += 1

                require_products(url_count, url)

            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {url}: {msg}")
                failures.append((url, msg))
            finally:
                context.close()

        browser.close()

    with open("lidl.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"✅ Scraped {len(all_data)} items total.")

    report_batch_failures(failures, len(links))


if __name__ == "__main__":
    scrape_lidl_pages()
