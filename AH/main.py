import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from links_dictionary import get_ah_links

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape_utils import (
    accept_common_cookies,
    configure_page,
    goto_resilient,
    launch_browser,
    report_batch_failures,
    require_products,
    strip_pagination_param,
    wait_for_products,
)


def scrape_category(page, url: str) -> list[dict]:
    goto_resilient(page, url)
    page.wait_for_timeout(2000)
    accept_common_cookies(page)
    wait_for_products(page, "article[data-testhook='product-card']", timeout=20000)

    click_count = 0
    while True:
        more_btn = page.query_selector('button[data-testhook="load-more"]')
        if more_btn and more_btn.is_enabled():
            print(f"➕ Click #{click_count + 1} on 'More results'")
            more_btn.click()
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            wait_for_products(page, "article[data-testhook='product-card']", timeout=10000)
            click_count += 1
        else:
            print("✅ 'More results' button not found or disabled.")
            break

    cards = page.query_selector_all("article[data-testhook='product-card']")
    print(f"🔍 Found {len(cards)} products.")

    products = []
    for card in cards:
        raw_text = card.inner_text().strip()
        img_card = card.query_selector("img[data-testhook='product-image']")
        img_src = img_card.get_attribute("src") if img_card else None
        products.append({"raw_text": raw_text, "image": img_src})
    return products


def main() -> None:
    os.makedirs("new_results", exist_ok=True)
    ah_links = get_ah_links()
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = launch_browser(p)
        for name, url in ah_links.items():
            clean_url = strip_pagination_param(url)
            print(f"Scraping category: {name} → {clean_url}")
            context = browser.new_context()
            page = context.new_page()
            configure_page(page, width=390, height=844)
            try:
                products = scrape_category(page, clean_url)
                require_products(len(products), name)
                filename = f"new_results/{name}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(products, f, indent=2, ensure_ascii=False)
                print(f"✅ {len(products)} products saved to {filename}")
            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {name}: {msg}")
                failures.append((clean_url, msg))
            finally:
                context.close()
        browser.close()

    report_batch_failures(failures, len(ah_links), label="categories")


if __name__ == "__main__":
    main()
