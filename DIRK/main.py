import json
import os
from playwright.sync_api import sync_playwright
from links2 import links
from playwright._impl._errors import TimeoutError

output_file = "dirk.json"

# Load existing data if file exists
if os.path.exists(output_file):
    with open(output_file, "r", encoding="utf-8") as f:
        product_data = json.load(f)
else:
    product_data = []

with sync_playwright() as p:
    browser = p.firefox.launch(headless=True)
    page = browser.new_page()

    print("🔄 Opening AH.nl...")
    page.set_viewport_size({"width": 390, "height": 844})
    page.set_extra_http_headers(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
        }
    )

    for url in links:
        print(f"🌐 Scraping: {url}")
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
        except TimeoutError:
            print(f"⚠️ Timeout on {url}, trying domcontentloaded instead...")
            page.goto(url, wait_until="domcontentloaded")

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
