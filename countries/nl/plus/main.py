import os
import sys
import time
from pathlib import Path

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

ROOT = _repo_root()
from category_utils import category_from_url
from plus_scrape import (
    DEFAULT_PDP_ENRICH_LIMIT,
    enrich_plus_entries_with_pdp_barcodes,
    scrape_plus_category_isolated,
)
from scrape_utils import (
    report_batch_failures,
    write_json_atomic,
)

OUTPUT_FILE = Path(__file__).resolve().parent / "plus.json"
DIAGNOSTICS_FILE = ROOT / "artifacts" / "plus-categories.json"


def scrape_plus_products(links: list[str], output_file: Path = OUTPUT_FILE) -> None:
    product_data: list[dict] = []
    seen: set[str] = set()
    failures: list[tuple[str, str]] = []
    diagnostics: list[dict] = []
    write_json_atomic(DIAGNOSTICS_FILE, diagnostics)
    enrich_limit = int(os.environ.get("PLUS_PDP_ENRICH_LIMIT", DEFAULT_PDP_ENRICH_LIMIT))

    with sync_playwright() as p:
        for url in links:
            started = time.monotonic()
            print(f"\n🌐 Scraping: {url}")
            try:
                category = category_from_url(url)
                batch = scrape_plus_category_isolated(
                    p, url, category=category, seen=seen
                )
                product_data.extend(batch)
                write_json_atomic(output_file, product_data)
                print(
                    f"🗂️ Scraped {len(batch)} products from {url}. "
                    f"Total: {len(product_data)}"
                )
                diagnostics.append({"url": url, "state": "complete", "new_products": len(batch),
                                    "duration_seconds": round(time.monotonic() - started, 2)})
            except Exception as err:
                msg = f"{type(err).__name__}: {err}"
                print(f"❌ Failed to scrape {url}: {msg}")
                failures.append((url, msg))
                diagnostics.append({"url": url, "state": "failed", "error_type": type(err).__name__,
                                    "duration_seconds": round(time.monotonic() - started, 2)})
            write_json_atomic(DIAGNOSTICS_FILE, diagnostics)
        print("🎯 Done.")

    # Every category must be complete before normalization can refresh timestamps.
    report_batch_failures(failures, len(links), max_failure_ratio=0)

    missing = sum(
        1 for entry in product_data if not entry.get("barcode") and entry.get("link")
    )
    if missing and enrich_limit > 0:
        print(
            f"🔎 Enriching up to {min(missing, enrich_limit)}/{missing} "
            "PLUS products missing barcode via PDP/detail..."
        )
        try:
            added = enrich_plus_entries_with_pdp_barcodes(
                product_data,
                limit=min(missing, enrich_limit),
            )
            write_json_atomic(output_file, product_data)
            print(f"📎 PDP enrichment added {added} barcodes")
        except Exception as enrich_err:
            print(f"⚠️ PDP enrichment failed: {type(enrich_err).__name__}: {enrich_err}")



if __name__ == "__main__":
    from links import links

    scrape_plus_products(links)
