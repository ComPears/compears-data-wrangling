import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from links2 import links

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

output_file = "JSONs/dirk.json"
os.makedirs("JSONs", exist_ok=True)

product_data: list[dict] = []
seen: set[str] = set()
failures: list[tuple[str, str]] = []

with sync_playwright() as p:
    browser = launch_browser(p)

    for url in links:
        print(f"🌐 Scraping: {url}")
        context = browser.new_context()
        page = context.new_page()
        configure_page(page, width=390, height=844)

        try:
            goto_resilient(page, url)
            page.wait_for_timeout(2000)
            accept_common_cookies(page)
            wait_for_products(page, "article[data-product-id]", timeout=20000)

            print("🔄 Loading all products...")
            category = category_from_url(url)
            cards = page.query_selector_all("article[data-product-id]")
            new_data = []

            for card in cards:
                raw_text = card.inner_text().strip()
                if raw_text in seen:
                    continue
                seen.add(raw_text)
                img_el = card.query_selector("img.main-image")
                img_src = img_el.get_attribute("src") if img_el else None
                new_data.append({"raw_text": raw_text, "image": img_src, "category": category})

            require_products(len(new_data), url)
            product_data.extend(new_data)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(product_data, f, indent=2, ensure_ascii=False)

            print(
                f"✅ Scraped {len(new_data)} products from this page. "
                f"Total saved: {len(product_data)}"
            )

        except Exception as err:
            msg = f"{type(err).__name__}: {err}"
            print(f"❌ Failed to scrape {url}: {msg}")
            failures.append((url, msg))
        finally:
            context.close()

    browser.close()

print(f"🏁 All done! {len(product_data)} total products saved.")
report_batch_failures(failures, len(links))
