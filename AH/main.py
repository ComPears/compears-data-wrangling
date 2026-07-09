import json
import os
import sys
from pathlib import Path

from links_dictionary import get_ah_links

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ah_api_client import (
    fetch_taxonomy_products,
    get_anonymous_token,
    product_to_raw_entry,
    taxonomy_id_from_url,
)
from category_utils import category_from_ah_key
from scrape_utils import report_batch_failures, require_products


def scrape_ah_products() -> None:
    os.makedirs("new_results", exist_ok=True)
    ah_links = get_ah_links()
    failures: list[tuple[str, str]] = []

    print("🔑 Fetching AH anonymous API token...")
    token = get_anonymous_token()

    for name, url in ah_links.items():
        taxonomy_id = taxonomy_id_from_url(url)
        if not taxonomy_id:
            failures.append((url, "Could not parse taxonomyId from URL"))
            continue

        print(f"Scraping category: {name} (taxonomy {taxonomy_id})")
        try:
            api_products = fetch_taxonomy_products(token, taxonomy_id)
            products = [product_to_raw_entry(product) for product in api_products]
            category = category_from_ah_key(name)
            for product in products:
                product["category"] = category

            require_products(len(products), name)
            filename = f"new_results/{name}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(products, f, indent=2, ensure_ascii=False)
            print(f"✅ {len(products)} products saved to {filename}")
        except Exception as err:
            msg = f"{type(err).__name__}: {err}"
            print(f"❌ Failed to scrape {name}: {msg}")
            failures.append((url, msg))

    report_batch_failures(failures, len(ah_links), label="categories")


if __name__ == "__main__":
    scrape_ah_products()
