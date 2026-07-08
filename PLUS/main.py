import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from typing import List, Optional
import re
import math

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape_utils import configure_page, goto_resilient


def get_product_count(page) -> Optional[int]:
    try:
        # Look for text containing "producten"
        product_count_element = page.get_by_text(" productenSorteer")
        if product_count_element:
            text = product_count_element.text_content()
            # Extract number using regex
            match = re.search(r"(\d+)", text)
            if match:
                return int(match.group(1))
    except:
        pass
    return None


def scrape_plus_products(links: List[str], output_file: str = "plus.json"):
    # Load existing data if file exists
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            product_data = json.load(f)
        print(f"📂 Loaded {len(product_data)} existing products")
    else:
        product_data = []

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        configure_page(page, width=1280, height=800)

        failures: list[tuple[str, str]] = []

        for url in links:
            print(f"\n🌐 Scraping: {url}")
            try:
                goto_resilient(page, url)
            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {url}: {msg}")
                failures.append((url, msg))
                continue

            print("⏳ Waiting for content to load")

            try:
                page.get_by_role("button", name="Accepteer").click()
                page.wait_for_url(url)
                print("🍪 Clicked accept cookie button")
            except:
                print("🍪 Cookie button not found or already accepted")

            try:
                page.get_by_role("link", name="Sluit winkel keuze").click()
                print("✖️ Closed the sidebar modal")
            except:
                print("🔍 Sidebar not present")

            number_of_products = get_product_count(page)

            if number_of_products is not None:
                click_space = math.ceil(number_of_products / 12) * 2
            else:
                click_space = 90

            try:
                page.locator("h1").click()
                count = 0
                for i in range(0, click_space):
                    page.keyboard.press("Space")
                    page.wait_for_timeout(1000)
                    page.keyboard.press("Space")

                    count += 1
                    
                    print(f"⬇️ Scrolling ... {count}/{click_space}")

            except:
                print("📍 Stopped Scrolling")

            page.wait_for_timeout(2000)

            try:
                cards = page.query_selector_all(".plp-item-wrapper")
                new_data = []

                for card in cards:
                    raw_text = card.inner_text().strip()
                    img = card.query_selector("img")
                    image_url = img.get_attribute("src") if img else None
                    new_data.append({"raw_text": raw_text, "image": image_url})

                product_data.extend(new_data)

                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(product_data, f, indent=2, ensure_ascii=False)

                print(
                    f"🗂️ Scraped {len(cards)} products from {url}. Total: {len(product_data)}"
                )

            except Exception as e:
                print(f"❌ Error scraping {url}: {e}")
                continue

        browser.close()
        print("🎯 Done.")

        if failures:
            print(f"⚠️ {len(failures)}/{len(links)} URLs failed:")
            for url, msg in failures:
                print(f"   - {url}: {msg}")
            if len(failures) / len(links) > 0.5:
                print("❌ More than half of PLUS URLs failed; exiting.")
                sys.exit(1)


# Example usage:
if __name__ == "__main__":
    from links import links  # Make sure this exists

    scrape_plus_products(links)
