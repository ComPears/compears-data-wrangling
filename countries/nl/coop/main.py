import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from links import links

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
from category_utils import category_from_coop_url
from plus_scrape import plus_cache_key, resolve_redirect_url, scrape_plus_category
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
                cache_key = plus_cache_key(coop_url, plus_url)
                if cache_key not in plus_cache:
                    print(f"   ↪ scraping {plus_url}")
                    plus_cache[cache_key] = scrape_plus_category(
                        page, plus_url, category=category, seen=seen
                    )
                else:
                    print(f"   ↪ reusing cached results for {plus_url}")

                url_products = [
                    {**entry, "category": category}
                    for entry in plus_cache[cache_key]
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

    # COOP redirects are lossy; allow more empty categories before failing CI.
    report_batch_failures(failures, len(urls), max_failure_ratio=0.30)


if __name__ == "__main__":
    scrape_coop_products(links, output_file=OUTPUT_FILE)
