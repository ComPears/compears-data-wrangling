import json
import os
import sys
from pathlib import Path

from links import get_aldi_links
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


def scrape_aldi_products(link_dict) -> None:
    os.makedirs("aldi_results", exist_ok=True)
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = launch_browser(p)

        for name, url in link_dict.items():
            print(f"🔄 Scraping: {name} → {url}")
            context = browser.new_context()
            page = context.new_page()
            configure_page(page)

            try:
                goto_resilient(page, url)
                page.wait_for_timeout(3000)
                accept_common_cookies(page)
                wait_for_products(page, "div.product-tile", timeout=20000)

                data: list[dict] = []
                seen: set[str] = set()

                while True:
                    cards = page.query_selector_all("div.product-tile")
                    for card in cards:
                        raw_text = card.inner_text().strip()
                        if raw_text in seen:
                            continue
                        seen.add(raw_text)
                        img_el = card.query_selector(
                            "img.product-tile__image-section__picture"
                        )
                        img_src = img_el.get_attribute("src") if img_el else None
                        data.append({"raw_text": raw_text, "image": img_src})

                    more_btn = page.locator("button:has-text('Meer tonen')")
                    if more_btn.count() and more_btn.first.is_visible():
                        more_btn.first.scroll_into_view_if_needed()
                        more_btn.first.click()
                        page.wait_for_timeout(3000)
                        wait_for_products(page, "div.product-tile", timeout=15000)
                    else:
                        break

                require_products(len(data), name)
                filename = f"aldi_results/{name}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"✅ {len(data)} items saved to {filename}")

            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {name}: {msg}")
                failures.append((url, msg))
            finally:
                context.close()

        browser.close()

    report_batch_failures(failures, len(link_dict), label="categories")


if __name__ == "__main__":
    scrape_aldi_products(get_aldi_links())
