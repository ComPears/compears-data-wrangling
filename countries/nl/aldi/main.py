import json
import os
import sys
from pathlib import Path

from links import get_aldi_links
from playwright.sync_api import sync_playwright

def _repo_root():
    from pathlib import Path
    import sys
    p = Path(__file__).resolve().parent
    for _ in range(8):
        if (p / "config" / "stores.json").is_file():
            s = str(p)
            if s not in sys.path:
                sys.path.insert(0, s)
            return p
        p = p.parent
    raise RuntimeError("Could not find compears-data-wrangling root")

_repo_root()
from category_utils import category_from_url
from scrape_utils import (
    accept_common_cookies,
    configure_page,
    goto_resilient,
    launch_browser,
    report_batch_failures,
    require_products,
    remove_stale_file,
    wait_for_products,
    write_json_atomic,
)

# Categories that intermittently return no products on aldi.nl.
OPTIONAL_CATEGORIES = {
    "kaas",
    "vleeswaren",
    "tapas",
    "wijn_wit",
    "chocolade",
    "snoep",
    "koek",
    "baby",
    "bbq_groente_fruit",
}


def extract_priced_cards(page, start_index: int = 0) -> list[dict]:
    # Tiles arrive before their asynchronous price data. Waiting for a tile (or
    # sleeping a fixed three seconds) accepted almost entirely unpriced runs.
    page.wait_for_function("""start => {
        const cards = [...document.querySelectorAll('div.product-tile')].slice(start);
        return cards.length > 0 && (
            cards.some(card => /\\d+[.,]\\d{2}/.test(
                card.querySelector('[data-testid$="-tag-current-price-amount"]')?.textContent || ''))
            || cards.every(card => /Niet verkrijgbaar/i.test(card.innerText)));
    }""", arg=start_index, timeout=20000)
    return page.locator("div.product-tile").evaluate_all("""cards => cards.map(card => {
        const text = suffix => card.querySelector(`[data-testid$="${suffix}"]`)?.textContent?.trim() || '';
        return {
            raw_text: card.innerText.trim(),
            name: text('-product-name'),
            price: text('-tag-current-price-amount'),
            size: text('-tag-sales-unit'),
            brand: text('-brand-name'),
            availability: /Niet verkrijgbaar/i.test(card.innerText) ? 'out_of_stock' : 'in_stock',
            productUrl: card.querySelector('a.product-tile__action')?.href || '',
            image: card.querySelector('img.product-tile__image-section__picture')?.src || ''
        };
    })""")


def scrape_aldi_products(link_dict) -> None:
    os.makedirs("aldi_results", exist_ok=True)
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = launch_browser(p)

        for name, url in link_dict.items():
            print(f"🔄 Scraping: {name} → {url}")
            filename = f"aldi_results/{name}.json"
            remove_stale_file(filename)
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
                category = category_from_url(url)
                previous_count = 0

                while True:
                    cards = extract_priced_cards(page, previous_count)
                    for card in cards:
                        identity = card["productUrl"] or card["raw_text"]
                        if identity in seen:
                            continue
                        seen.add(identity)
                        data.append({**card, "category": category})

                    more_btn = page.locator("button:has-text('Meer tonen')")
                    if more_btn.count() and more_btn.first.is_visible():
                        previous_count = len(cards)
                        more_btn.first.scroll_into_view_if_needed()
                        more_btn.first.click()
                        page.wait_for_function(
                            "count => document.querySelectorAll('div.product-tile').length > count",
                            arg=len(cards), timeout=15000,
                        )
                    else:
                        break

                require_products(len(data), name, min_count=0 if name in OPTIONAL_CATEGORIES else 1)
                if len(data) == 0 and name in OPTIONAL_CATEGORIES:
                    print(f"⚠️ Optional category {name} returned 0 products; skipping")
                    continue
                write_json_atomic(filename, data)
                print(f"✅ {len(data)} items saved to {filename}")

            except Exception as err:
                if name in OPTIONAL_CATEGORIES:
                    print(f"⚠️ Optional category {name} failed: {err}")
                    continue
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {name}: {msg}")
                failures.append((url, msg))
            finally:
                context.close()

        browser.close()

    report_batch_failures(failures, len(link_dict), label="categories")


if __name__ == "__main__":
    scrape_aldi_products(get_aldi_links())
