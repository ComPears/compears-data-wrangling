import json
import math
import re
import sys
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import sync_playwright

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


def get_product_count(page) -> Optional[int]:
    try:
        product_count_element = page.get_by_text(" productenSorteer")
        if product_count_element:
            text = product_count_element.text_content()
            match = re.search(r"(\d+)", text)
            if match:
                return int(match.group(1))
    except Exception:
        pass
    return None


def scrape_plus_products(links: List[str], output_file: str = "plus.json") -> None:
    product_data: list[dict] = []
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = launch_browser(p)

        for url in links:
            print(f"\n🌐 Scraping: {url}")
            context = browser.new_context()
            page = context.new_page()
            configure_page(page, width=1280, height=800)

            try:
                goto_resilient(page, url)
                print("⏳ Waiting for content to load")
                accept_common_cookies(page)

                try:
                    page.get_by_role("link", name="Sluit winkel keuze").click()
                    print("✖️ Closed the sidebar modal")
                except Exception:
                    print("🔍 Sidebar not present")

                number_of_products = get_product_count(page)
                click_space = math.ceil(number_of_products / 12) * 2 if number_of_products else 90

                try:
                    page.locator("h1").click()
                    for i in range(click_space):
                        page.keyboard.press("Space")
                        page.wait_for_timeout(1000)
                        page.keyboard.press("Space")
                        print(f"⬇️ Scrolling ... {i + 1}/{click_space}")
                except Exception:
                    print("📍 Stopped Scrolling")

                page.wait_for_timeout(2000)
                wait_for_products(page, ".plp-item-wrapper", timeout=20000)

                cards = page.query_selector_all(".plp-item-wrapper")
                category = category_from_url(url)
                new_data = []
                for card in cards:
                    raw_text = card.inner_text().strip()
                    img = card.query_selector("img")
                    image_url = img.get_attribute("src") if img else None
                    new_data.append({"raw_text": raw_text, "image": image_url, "category": category})

                require_products(len(new_data), url)
                product_data.extend(new_data)

                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(product_data, f, indent=2, ensure_ascii=False)

                print(
                    f"🗂️ Scraped {len(cards)} products from {url}. "
                    f"Total: {len(product_data)}"
                )

            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {url}: {msg}")
                failures.append((url, msg))
            finally:
                context.close()

        browser.close()
        print("🎯 Done.")

    report_batch_failures(failures, len(links))


if __name__ == "__main__":
    from links import links

    scrape_plus_products(links)
