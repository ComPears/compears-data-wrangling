import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from links import links

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape_utils import configure_page, goto_resilient


def scrape_coop_products(urls, output_file):
    if isinstance(urls, str):
        urls = [urls]

    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            product_data = json.load(f)
        print(f"📂 Loaded {len(product_data)} existing products")
    else:
        product_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        configure_page(page, width=1280, height=800)

        all_products = []
        failures: list[tuple[str, str]] = []

        for url in urls:
            print(f"🔄 Opening {url}...")
            try:
                goto_resilient(page, url)
            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {url}: {msg}")
                failures.append((url, msg))
                continue

            page.wait_for_timeout(2000)

            print("🔄 Scraping paginated results...")
            while True:
                try:
                    cards = page.query_selector_all(".product-card")

                    for card in cards:
                        raw_text = card.inner_text().strip()
                        img = card.query_selector("img")
                        img_src = img.get_attribute("src") if img else None
                        all_products.append({"raw_text": raw_text, "image": img_src})

                    product_data.extend(all_products)

                    print(
                        f"📦 Found {len(cards)} on this page,  Scraped {len(all_products)} products. Total so far: {len(product_data)}"
                    )
                    try:
                        next_btn = page.locator(
                            "custom-product-list-paging a:not(.product-list-paging__previous) button.button__svg--pagination"
                        )

                        if next_btn and next_btn.is_visible():
                            next_btn.click()
                            print("➡️ Clicked next page")
                            page.wait_for_timeout(3000)
                        else:
                            print("✅ No more pages.")
                            break

                    except Exception as e:
                        print("✅ No more pages.",e)

                except Exception as e:
                    print(f"⚠️ Error during pagination: {e}")
                    break


            # 💾 Save to JSON
            # os.makedirs("new_results", exist_ok=True)

            filename = f"{output_file}"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(product_data, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved {len(product_data)} products to {filename}")


        browser.close()

    if failures:
        print(f"⚠️ {len(failures)}/{len(urls)} URLs failed:")
        for url, msg in failures:
            print(f"   - {url}: {msg}")
        if len(failures) / len(urls) > 0.5:
            print("❌ More than half of COOP URLs failed; exiting.")
            sys.exit(1)


# 🔁 Run the scraper
scrape_coop_products(links, output_file="coop.json")
