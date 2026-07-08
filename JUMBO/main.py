import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape_utils import (
    accept_common_cookies,
    configure_page,
    goto_resilient,
    launch_browser,
    report_batch_failures,
    require_products,
    wait_for_products,
)

from links import links


def get_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    last_part = path.rstrip("/").split("/")[-1]
    return last_part or "unknown"


def scrape_jumbo_products(link_list) -> None:
    os.makedirs("JSONs", exist_ok=True)
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = launch_browser(p)

        for link in link_list:
            filename_suffix = get_filename_from_url(link)
            print(f"\n🔄 Scraping: {link}")
            context = browser.new_context()
            page = context.new_page()
            configure_page(page)

            try:
                goto_resilient(page, link)
                page.wait_for_timeout(3000)
                accept_common_cookies(page)

                seen: set[str] = set()
                data: list[dict] = []
                click_count = 0

                while True:
                    wait_for_products(page, "article.product-container", timeout=20000)
                    cards = page.query_selector_all("article.product-container")
                    print(f"🔍 Found {len(cards)} product cards on this page")

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

                    more_btn = page.locator("button:has-text('Volgende')")
                    if more_btn.count() and more_btn.first.is_visible() and more_btn.first.is_enabled():
                        print(f"➕ Click #{click_count + 1} on 'Volgende'")
                        more_btn.first.scroll_into_view_if_needed()
                        more_btn.first.click()
                        try:
                            page.wait_for_load_state("networkidle", timeout=30000)
                        except Exception:
                            pass
                        page.wait_for_timeout(2000)
                        wait_for_products(page, "article.product-container", timeout=20000)
                        click_count += 1

                        cards_after = page.query_selector_all("article.product-container")
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

                require_products(len(data), link)
                print(f"✅ Total unique products: {len(data)}")
                output_file = f"JSONs/jumbo_products_{filename_suffix}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {link}: {msg}")
                failures.append((link, msg))
            finally:
                context.close()

        browser.close()

    report_batch_failures(failures, len(link_list))


if __name__ == "__main__":
    scrape_jumbo_products(links)
