import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from links2 import links

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape_utils import configure_page, goto_resilient

output_file = "JSONs/dirk.json"

# Load existing data if file exists
if os.path.exists(output_file):
    with open(output_file, "r", encoding="utf-8") as f:
        product_data = json.load(f)
else:
    product_data = []

with sync_playwright() as p:
    browser = p.firefox.launch(headless=True)
    page = browser.new_page()
    configure_page(page, width=390, height=844)

    failures: list[tuple[str, str]] = []

    for url in links:
        print(f"🌐 Scraping: {url}")
        try:
            goto_resilient(page, url)
        except Exception as err:
            msg = f"{type(err).__name__}: {err}"
            print(f"❌ Failed to scrape {url}: {msg}")
            failures.append((url, msg))
            continue

        page.wait_for_timeout(2000)
        print("🔄 Loading all products...")

        try:
            cards = page.query_selector_all("article[data-product-id]")
            new_data = []

            for card in cards:
                raw_text = card.inner_text().strip()
                img_el = card.query_selector("img.main-image")
                img_src = img_el.get_attribute("src") if img_el else None
                new_data.append({"raw_text": raw_text, "image": img_src})

            product_data.extend(new_data)

            # Save progress after every page
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(product_data, f, indent=2, ensure_ascii=False)

            print(
                f"✅ Scraped {len(cards)} products from this page. Total saved: {len(product_data)}"
            )

        except Exception as e:
            print(f"❌ Error scraping {url}: {e}")
            continue

        

    print(f"🏁 All done! {len(product_data)} total products saved.")
    browser.close()

if failures:
    print(f"⚠️ {len(failures)}/{len(links)} URLs failed:")
    for url, msg in failures:
        print(f"   - {url}: {msg}")
    if len(failures) / len(links) > 0.5:
        print("❌ More than half of DIRK URLs failed; exiting.")
        sys.exit(1)
