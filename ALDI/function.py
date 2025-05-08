import json
import os
from links import get_aldi_links,add_remaining_links
from playwright.sync_api import sync_playwright


def scrape_aldi_products(link_dict):
    os.makedirs("aldi_results", exist_ok=True)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1600, "height": 900})
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
        })

        for name, url in link_dict.items():
            print(f"🔄 Scraping: {name} → {url}")
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(3000)

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

# Run it
if __name__ == "__main__":
    scrape_aldi_products(add_remaining_links())
