import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from links import links

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape_utils import configure_page, goto_resilient


def scrape_lidl_pages():
    all_data = []
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        configure_page(page)

        for url in links:
            print(f"🌐 Scraping: {url}")
            try:
                goto_resilient(page, url)
                page.wait_for_timeout(2000)
            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {url}: {msg}")
                failures.append((url, msg))
                continue

            try:
                accept_btn = page.query_selector("button:has-text('Accepteren')")
                if accept_btn:
                    accept_btn.click()
            except:
                pass

            print("🔄 Scrolling to load all products...")
            for _ in range(30):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(400)

            cards = page.query_selector_all("div.odsc-tile")
            print(f"📦 Found {len(cards)} product cards.")

            for card in cards:
                text = card.inner_text().strip()
                img = card.query_selector("img.odsc-image-gallery__image")
                src = img.get_attribute("src") if img else None
                all_data.append({"raw_text": text, "image": src})

        browser.close()

    with open("lidl.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Scraped {len(all_data)} items total.")

    if failures:
        print(f"⚠️ {len(failures)}/{len(links)} URLs failed:")
        for url, msg in failures:
            print(f"   - {url}: {msg}")
        if len(failures) / len(links) > 0.5:
            print("❌ More than half of LIDL URLs failed; exiting.")
            sys.exit(1)


# Run it
scrape_lidl_pages()

