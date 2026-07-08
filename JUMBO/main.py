import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape_utils import configure_page, goto_resilient, wait_for_products

from links import links  # Your list of product URLs


def get_filename_from_url(url):
    path = urlparse(url).path
    last_part = path.rstrip("/").split("/")[-1]
    return last_part or "unknown"


def scrape_jumbo_products(link_list):
    os.makedirs("JSONs", exist_ok=True)
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        configure_page(page)

        for link in link_list:
            filename_suffix = get_filename_from_url(link)
            print(f"\n🔄 Scraping: {link}")

            try:
                goto_resilient(page, link)
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
                    wait_for_products(page, "article.product-container")
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
                            try:
                                page.wait_for_load_state("networkidle", timeout=30000)
                            except Exception:
                                pass
                            wait_for_products(page, "article.product-container")
                            click_count += 1

                            cards_after = page.query_selector_all(
                                "article.product-container"
                            )
                            if not cards_after:
                                page.wait_for_timeout(5000)
                                wait_for_products(
                                    page, "article.product-container", timeout=20000
                                )
                                cards_after = page.query_selector_all(
                                    "article.product-container"
                                )
                            if not cards_after:
                                print("⚠️ No products after pagination; stopping.")
                                break
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

            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {link}: {msg}")
                failures.append((link, msg))

        browser.close()

    if failures:
        print(f"⚠️ {len(failures)}/{len(link_list)} URLs failed:")
        for url, msg in failures:
            print(f"   - {url}: {msg}")

        if len(failures) / len(link_list) > 0.5:
            print("❌ More than half of Jumbo categories failed; exiting.")
            sys.exit(1)


if __name__ == "__main__":
    scrape_jumbo_products(links)
