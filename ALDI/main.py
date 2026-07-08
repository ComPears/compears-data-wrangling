import json
import os
import sys
from pathlib import Path

from links import get_aldi_links
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape_utils import configure_page, goto_resilient


def scrape_aldi_products(link_dict):
    os.makedirs("aldi_results", exist_ok=True)
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        configure_page(page)

        for name, url in link_dict.items():
            print(f"🔄 Scraping: {name} → {url}")
            try:
                goto_resilient(page, url)
                page.wait_for_timeout(3000)
            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {name}: {msg}")
                failures.append((url, msg))
                continue

            data, seen = [], set()

            while True:
                cards = page.query_selector_all("div.product-tile")
                for card in cards:
                    raw_text = card.inner_text().strip()
                    if raw_text in seen: continue
                    seen.add(raw_text)
                    img_el = card.query_selector("img.product-tile__image-section__picture")
                    img_src = img_el.get_attribute("src") if img_el else None
                    data.append({"raw_text": raw_text, "image": img_src})

                more_btn = page.locator("button:has-text('Meer tonen')")
                if more_btn.is_visible():
                    more_btn.scroll_into_view_if_needed()
                    more_btn.click()
                    page.wait_for_timeout(3000)
                else:
                    break

            filename = f"aldi_results/{name}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✅ {len(data)} items saved to {filename}")

        browser.close()

    if failures:
        print(f"⚠️ {len(failures)}/{len(link_dict)} categories failed:")
        for url, msg in failures:
            print(f"   - {url}: {msg}")
        if len(failures) / len(link_dict) > 0.5:
            print("❌ More than half of ALDI categories failed; exiting.")
            sys.exit(1)


# Run it
if __name__ == "__main__":
    scrape_aldi_products(get_aldi_links())
