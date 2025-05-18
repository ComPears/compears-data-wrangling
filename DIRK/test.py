import json
from playwright.sync_api import sync_playwright
from links import links


def scrape_lidl_pages():
    all_data = []

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1600, "height": 900})
        page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
            }
        )

        for url in links:
            print(f"🌐 Scraping: {url}")
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(2000)

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

            cards = page.query_selector_all("div.product-cards")
            print(f"📦 Found {len(cards)} product cards.")

            for card in cards:
                print(card.inner_text().strip())

            # for card in cards:
            #     text = card.inner_text().strip()
            #     img = card.query_selector("img.odsc-image-gallery__image")
            #     src = img.get_attribute("src") if img else None
            #     all_data.append({"raw_text": text, "image": src})

        browser.close()

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Scraped {len(all_data)} items total.")


# Run it
scrape_lidl_pages()
