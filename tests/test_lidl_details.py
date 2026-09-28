import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "countries/uk/_shared"))
from lidl_details import enrich_pack_sizes, size_from_product_html, valid_product_url
from uk_product import structure_raw_products
from product_sanitize import sanitize_entry_with_reason

URL = "https://www.lidl.co.uk/p/cacaolat-chocolate-milk/p10055014"


def html(size="6x200ml", product_id="10055014"):
    # Minimized from the retailer's live product page on 2026-09-27.
    return (f'<span data-qa-label="erp-number">{product_id}</span>'
            f'<div class="short-description__description">{size}</div>'
            '<div class="short-description__summary">Save 50p. £2.91/l</div>')


def row():
    return {"n": "Chocolate Milk", "p": "3.49", "s": "", "i": URL,
            "retailerProductId": "10055014", "bn": "CACAOLAT",
            "retailerCategory": "Food", "categorySource": "lidl_product_grid"}


class LidlDetailsTests(unittest.TestCase):
    def test_explicit_multipack_and_identity(self):
        self.assertEqual(size_from_product_html(html(), "10055014"), "6 × 200 ml")
        self.assertIsNone(size_from_product_html(html(product_id="999"), "10055014"))
        self.assertIsNone(size_from_product_html('<div class="short-description__description">500g</div>', "10055014"))

    def test_unit_prices_nutrition_and_ambiguous_variants_are_not_sizes(self):
        for size in ("£2.91/l", "per 100g", "500g / 750g", "contains 10g protein", "SAVE 20%", "0g"):
            with self.subTest(size=size):
                self.assertIsNone(size_from_product_html(html(size), "10055014"))
        self.assertIsNone(size_from_product_html(html("500g") + html("750g"), "10055014"))

    def test_mobile_duplicate_and_nested_markup(self):
        self.assertEqual(size_from_product_html(html("<b>500g</b>") * 2, "10055014"), "500 g")

    def test_enrichment_survives_structure_and_contract(self):
        rows = [row()]
        stats = enrich_pack_sizes(rows, fetch=lambda *a, **k: html())
        self.assertEqual(stats["enriched"], 1)
        cleaned, reason = sanitize_entry_with_reason(structure_raw_products(rows)[0], country="uk", store="lidl-uk")
        self.assertIsNone(reason)
        self.assertEqual(cleaned["quantity"]["totalValue"], 1200)
        self.assertEqual(cleaned["quantity"]["baseUnit"], "ml")
        self.assertEqual(cleaned["quantitySourceUrl"], URL)
        self.assertEqual(cleaned["quantitySource"], "retailer_product_description")
        self.assertIn("quantityObservedAt", cleaned)

    def test_existing_quantity_unchanged_and_duplicates_fetched_once(self):
        existing = {**row(), "s": "200 ml"}
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            return html()
        rows = [existing, row(), row()]
        stats = enrich_pack_sizes(rows, fetch=fetch)
        self.assertEqual(calls, [URL])
        self.assertEqual(existing["s"], "200 ml")
        self.assertEqual(stats["attempted"], 1)
        self.assertEqual(stats["enriched"], 2)

    def test_budget_and_request_limit(self):
        calls = []
        def fetch(url, **kwargs):
            calls.append(kwargs["timeout"])
            return html()
        ticks = iter([0, 1, 301])
        other = {**row(), "i": URL.replace("10055014", "10055015"), "retailerProductId": "10055015"}
        stats = enrich_pack_sizes([row(), other], fetch=fetch, clock=lambda: next(ticks))
        self.assertEqual(stats["attempted"], 1)
        self.assertEqual(calls, [8])
        self.assertEqual(enrich_pack_sizes([row()], limit=0, fetch=fetch)["attempted"], 0)

    def test_failed_fetch_preserves_missing_size(self):
        def fetch(*a, **k):
            raise TimeoutError("timeout")
        rows = [row()]
        self.assertEqual(enrich_pack_sizes(rows, fetch=fetch)["unavailable"], 1)
        self.assertEqual(rows[0]["s"], "")

    def test_urls_fail_closed(self):
        for url in ("http://www.lidl.co.uk/p/x/p10055014", URL + "?next=http://localhost",
                    URL.replace("www.lidl.co.uk", "www.lidl.co.uk.evil.test"),
                    URL.replace("10055014", "999"), URL.replace("www.lidl.co.uk", "localhost")):
            self.assertFalse(valid_product_url(url, "10055014"))

    def test_daily_pipeline_enriches_before_structure(self):
        from config.paths import store_config
        steps = store_config("uk", "lidl-uk")["pipeline"]
        self.assertLess(steps.index("enrich.py"), steps.index("structure.py"))
