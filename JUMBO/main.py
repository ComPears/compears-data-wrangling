import json
import os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from links import links  # Your list of product URLs


def get_filename_from_url(url):
    path = urlparse(url).path
    # Remove trailing slash if present and take the last segment
    last_part = path.rstrip("/").split("/")[-1]
    return last_part or "unknown"


def scrape_jumbo_products(link_list):
    os.makedirs("JSONs", exist_ok=True)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1600, "height": 900})
        page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
            }
        )

        for link in link_list:
            filename_suffix = get_filename_from_url(link)
            print(f"\n🔄 Scraping: {link}")
            page.goto(link, wait_until="load", timeout=60000)
            page.wait_for_timeout(3000)

            try:
                print("🍪 Trying to accept cookie consent...")
                consent_button = page.locator("button:has-text('Akkoord')")
                if consent_button.is_visible():
                    consent_button.click()
                    print("✅ Cookie banner closed.")
                    page.wait_for_timeout(2000)
            except Exception as e:
                print(f"⚠️ Cookie banner not handled: {e}")

            seen = set()
            data = []
            click_count = 0

            while True:
                cards = page.query_selector_all("article.product-container")
                print(f"🔍 Found {len(cards)} product cards on this page")

                new_items = 0
                for card in cards:
                    raw_text = card.inner_text().strip()
                    if raw_text in seen:
                        continue
                    seen.add(raw_text)

                    img = card.query_selector(
                        'div.product-image img[data-testid="jum-product-image"]'
                    )
                    src = img.get_attribute("src") if img else None

                    data.append({"raw_text": raw_text, "image": src})
                    new_items += 1

                try:
                    more_btn = page.locator("button:has-text('Volgende')")
                    if more_btn.is_visible() and more_btn.is_enabled():
                        print(f"➕ Click #{click_count + 1} on 'Volgende'")
                        more_btn.scroll_into_view_if_needed()
                        more_btn.click()
                        page.wait_for_timeout(3000)
                        click_count += 1
                    else:
                        print("✅ No more 'Volgende' button or it's disabled.")
                        break
                except Exception as e:
                    print(f"⚠️ Error during 'Volgende' click: {e}")
                    break

            print(f"✅ Total unique products: {len(data)}")
            output_file = f"JSONs/jumbo_products_{filename_suffix}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        browser.close()


if __name__ == "__main__":
    scrape_jumbo_products(links)
