import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from links import links

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from category_utils import category_from_coop_url
from plus_scrape import resolve_redirect_url, scrape_plus_category
from scrape_utils import (
    PLUS_USER_AGENT,
    configure_page,
    launch_browser,
    report_batch_failures,
    require_products,
    write_json_atomic,
)

OUTPUT_FILE = Path(__file__).resolve().parent / "coop.json"


def scrape_coop_products(urls, output_file: Path = OUTPUT_FILE) -> None:
    if isinstance(urls, str):
        urls = [urls]

    product_data: list[dict] = []
    seen: set[str] = set()
    failures: list[tuple[str, str]] = []
    plus_cache: dict[str, list[dict]] = {}

    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context(
            user_agent=PLUS_USER_AGENT,
            locale="nl-NL",
        )

        for coop_url in urls:
            print(f"🔄 Resolving {coop_url}...")
            page = context.new_page()
            configure_page(page, width=1280, height=800)
            try:
                plus_url = resolve_redirect_url(coop_url)
                if "plus.nl" not in plus_url:
                    raise RuntimeError(f"Unexpected redirect target: {plus_url}")

                category = category_from_coop_url(coop_url)
                if plus_url not in plus_cache:
                    print(f"   ↪ scraping {plus_url}")
                    plus_cache[plus_url] = scrape_plus_category(
                        page, plus_url, category=category, seen=seen
                    )
                else:
                    print(f"   ↪ reusing cached results for {plus_url}")

                url_products = [
                    {**entry, "category": category}
                    for entry in plus_cache[plus_url]
                ]
                require_products(len(url_products), coop_url)
                product_data.extend(url_products)

            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {coop_url}: {msg}")
                failures.append((coop_url, msg))
            finally:
                page.close()

            write_json_atomic(output_file, product_data)
            print(f"✅ Saved {len(product_data)} products to {output_file}")

        context.close()
        browser.close()

    report_batch_failures(failures, len(urls))


if __name__ == "__main__":
    scrape_coop_products(links, output_file=OUTPUT_FILE)
