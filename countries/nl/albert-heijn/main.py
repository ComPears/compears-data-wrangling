import json
import os
import sys
import time
from pathlib import Path

from links_dictionary import get_ah_links

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
from ah_api_client import (
    DEFAULT_DETAIL_ENRICH_LIMIT,
    enrich_raw_entries_with_detail_barcodes,
    fetch_taxonomy_products,
    get_anonymous_token,
    product_to_raw_entry,
    taxonomy_id_from_url,
)
from category_utils import category_from_ah_key
from scrape_utils import report_batch_failures, require_products, remove_stale_file, write_json_atomic


def scrape_ah_products() -> None:
    os.makedirs("new_results", exist_ok=True)
    ah_links = get_ah_links()
    failures: list[tuple[str, str]] = []
    enrich_limit = int(os.environ.get("AH_DETAIL_ENRICH_LIMIT", DEFAULT_DETAIL_ENRICH_LIMIT))

    print("🔑 Fetching AH anonymous API token...")
    token = get_anonymous_token()

    for name, url in ah_links.items():
        taxonomy_id = taxonomy_id_from_url(url)
        if not taxonomy_id:
            failures.append((url, "Could not parse taxonomyId from URL"))
            continue

        print(f"Scraping category: {name} (taxonomy {taxonomy_id})")
        filename = f"new_results/{name}.json"
        remove_stale_file(filename)
        try:
            api_products = fetch_taxonomy_products(token, taxonomy_id)
            products = [product_to_raw_entry(product) for product in api_products]
            category = category_from_ah_key(name)
            for product in products:
                product["category"] = category

            missing = sum(1 for product in products if not product.get("barcode"))
            if missing and enrich_limit > 0:
                print(
                    f"🔎 Enriching up to {min(missing, enrich_limit)}/{missing} "
                    "products missing barcode via detail API..."
                )
                try:
                    added = enrich_raw_entries_with_detail_barcodes(
                        token,
                        products,
                        limit=min(missing, enrich_limit),
                    )
                    print(f"📎 Detail enrichment added {added} barcodes")
                except Exception as enrich_err:
                    print(
                        f"⚠️ Detail enrichment failed for {name}: "
                        f"{type(enrich_err).__name__}: {enrich_err}"
                    )

            require_products(len(products), name)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(products, f, indent=2, ensure_ascii=False)
            with_barcode = sum(1 for product in products if product.get("barcode"))
            print(
                f"✅ {len(products)} products saved to {filename} "
                f"({with_barcode} with barcode)"
            )
        except Exception as err:
            msg = f"{type(err).__name__}: {err}"
            print(f"❌ Failed to scrape {name}: {msg}")
            failures.append((url, msg))

        time.sleep(1.0)

    report_batch_failures(failures, len(ah_links), label="categories")


if __name__ == "__main__":
    scrape_ah_products()
