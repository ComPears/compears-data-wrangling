import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from links import links

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape_utils import (
    accept_common_cookies,
    configure_page,
    goto_resilient,
    launch_browser,
    report_batch_failures,
    require_products,
    wait_for_products,
)


def scrape_coop_products(urls, output_file: str = "coop.json") -> None:
    if isinstance(urls, str):
        urls = [urls]

    product_data: list[dict] = []
    seen: set[str] = set()
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = launch_browser(p)

        for url in urls:
            print(f"🔄 Opening {url}...")
            context = browser.new_context()
            page = context.new_page()
            configure_page(page, width=1280, height=800)

            try:
                goto_resilient(page, url)
                page.wait_for_timeout(2000)
                accept_common_cookies(page)
                wait_for_products(page, ".product-card", timeout=20000)

                url_products: list[dict] = []
                page_num = 1

                while True:
                    cards = page.query_selector_all(".product-card")
                    new_on_page = 0

                    for card in cards:
                        raw_text = card.inner_text().strip()
                        if raw_text in seen:
                            continue
                        seen.add(raw_text)
                        img = card.query_selector("img")
                        img_src = img.get_attribute("src") if img else None
                        entry = {"raw_text": raw_text, "image": img_src}
                        url_products.append(entry)
                        new_on_page += 1

                    print(
                        f"📦 Page {page_num}: {len(cards)} cards, "
                        f"{new_on_page} new. Category total: {len(url_products)}"
                    )

                    next_btn = page.locator(
                        "custom-product-list-paging "
                        "a:not(.product-list-paging__previous) "
                        "button.button__svg--pagination"
                    )
                    if next_btn.count() and next_btn.first.is_visible():
                        next_btn.first.click()
                        page.wait_for_timeout(3000)
                        wait_for_products(page, ".product-card", timeout=15000)
                        page_num += 1
                    else:
                        print("✅ No more pages.")
                        break

                require_products(len(url_products), url)
                product_data.extend(url_products)

            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {url}: {msg}")
                failures.append((url, msg))
            finally:
                context.close()

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(product_data, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved {len(product_data)} products to {output_file}")

        browser.close()

    report_batch_failures(failures, len(urls))


if __name__ == "__main__":
    scrape_coop_products(links, output_file="coop.json")
