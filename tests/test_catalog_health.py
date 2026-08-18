from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ah_api_client import (
    barcode_from_detail_payload,
    enrich_raw_entries_with_detail_barcodes,
    product_to_raw_entry,
)
from barcode_utils import (
    barcode_from_product_code,
    extract_barcode_from_entry,
    extract_barcode_from_html,
    normalize_barcode,
)
from dirk_barcode import extract_card_barcode, extract_pdp_barcode
from plus_scrape import _product_from_plp, extract_pdp_barcode as plus_extract_pdp_barcode
from scripts.catalog_health import analyze_catalog


EAN13 = "4006381333931"
EAN8 = "96385074"
DUTCH_EAN = "8718452709458"


class FakeScript:
    def __init__(self, payload: str):
        self.payload = payload

    def text_content(self) -> str:
        return self.payload


class FakeCard:
    def __init__(self, attributes=None, scripts=None):
        self.attributes = attributes or {}
        self.scripts = scripts or []

    def get_attribute(self, key):
        return self.attributes.get(key)

    def query_selector_all(self, _selector):
        return self.scripts


class BarcodeExtractionTests(unittest.TestCase):
    def test_normalizes_valid_ean_and_rejects_invalid(self):
        self.assertEqual(normalize_barcode(EAN13), EAN13)
        self.assertIsNone(normalize_barcode("4006381333932"))
        # AH detail API returns GTIN-14 with a leading zero
        self.assertEqual(normalize_barcode("0" + EAN13), EAN13)

    def test_does_not_mine_arbitrary_urls_or_text(self):
        entry = {
            "image": f"https://cdn.example/{EAN13}.png",
            "raw_text": f"special {EAN13}",
        }
        self.assertIsNone(extract_barcode_from_entry(entry))

    def test_ah_and_plus_use_explicit_schema_fields(self):
        ah = product_to_raw_entry({"title": "Test", "currentPrice": 1.25, "gtin13": EAN13})
        plus = _product_from_plp({"Name": "Test", "OriginalPrice": 2, "EAN": EAN13})
        self.assertEqual(ah["barcode"], EAN13)
        self.assertEqual(plus["barcode"], EAN13)

    def test_internal_product_ids_are_not_used_as_barcodes(self):
        ah = product_to_raw_entry({"title": "Test", "currentPrice": 1, "webshopId": EAN13})
        plus = _product_from_plp({"Name": "Test", "OriginalPrice": 2, "Product_Code": EAN13})
        self.assertIsNone(ah["barcode"])
        self.assertIsNone(plus["barcode"])

    def test_ah_detail_payload_extracts_gtin(self):
        detail = {
            "productCard": {
                "webshopId": 12345,
                "title": "Melk",
                "gtin13": DUTCH_EAN,
            }
        }
        self.assertEqual(barcode_from_detail_payload(detail), DUTCH_EAN)
        self.assertEqual(
            barcode_from_detail_payload({"tradeItemNumber": EAN13}),
            EAN13,
        )
        raw = product_to_raw_entry(
            {"title": "Melk", "currentPrice": 1.0, "webshopId": 99, "tradeItemNumber": DUTCH_EAN}
        )
        self.assertEqual(raw["barcode"], DUTCH_EAN)
        self.assertEqual(raw["webshopId"], "99")

    def test_ah_detail_enrichment_fills_missing_barcodes(self):
        entries = [
            {"raw_text": "A", "webshopId": "1", "barcode": None},
            {"raw_text": "B", "webshopId": "2", "barcode": DUTCH_EAN},
            {"raw_text": "C", "barcode": None},
        ]
        with patch(
            "ah_api_client.fetch_product_detail",
            return_value={"productCard": {"gtin13": EAN13}},
        ), patch("ah_api_client.time.sleep"):
            added = enrich_raw_entries_with_detail_barcodes(
                "tok", entries, limit=10, workers=1
            )
        self.assertEqual(added, 1)
        self.assertEqual(entries[0]["barcode"], EAN13)
        self.assertEqual(entries[1]["barcode"], DUTCH_EAN)
        self.assertIsNone(entries[2]["barcode"])

    def test_dirk_reads_data_attribute_or_product_json_ld(self):
        self.assertEqual(extract_card_barcode(FakeCard({"data-ean": EAN13})), EAN13)
        card = FakeCard(scripts=[FakeScript(json.dumps({"@type": "Product", "gtin8": EAN8}))])
        self.assertEqual(extract_card_barcode(card), EAN8)

    def test_dirk_pdp_json_ld_extraction(self):
        html = f"""
        <html><head>
        <script type="application/ld+json">
        {{"@type": "Product", "name": "Melk", "gtin13": "{DUTCH_EAN}"}}
        </script>
        </head></html>
        """
        self.assertEqual(extract_pdp_barcode(html), DUTCH_EAN)
        self.assertEqual(
            extract_pdp_barcode({"@type": "Product", "gtin": EAN13}),
            EAN13,
        )
        graph = {
            "@graph": [
                {"@type": "WebPage", "name": "x"},
                {"@type": "Product", "ean": EAN8},
            ]
        }
        self.assertEqual(extract_pdp_barcode(graph), EAN8)

    def test_plus_pdp_json_ld_and_next_data(self):
        html = f"""
        <script type="application/ld+json">
        {{"@type":"Product","gtin13":"{DUTCH_EAN}"}}
        </script>
        """
        self.assertEqual(plus_extract_pdp_barcode(html), DUTCH_EAN)

        next_html = f"""
        <script id="__NEXT_DATA__" type="application/json">
        {{"props":{{"pageProps":{{"product":{{"gtin":"{EAN13}"}}}}}}}}
        </script>
        """
        self.assertEqual(plus_extract_pdp_barcode(next_html), EAN13)
        self.assertEqual(
            plus_extract_pdp_barcode({"ProductDetail": {"EAN": DUTCH_EAN}}),
            DUTCH_EAN,
        )

    def test_product_code_only_when_real_gtin(self):
        self.assertEqual(barcode_from_product_code(DUTCH_EAN), DUTCH_EAN)
        # Short internal ids must not pad into false EANs.
        self.assertIsNone(barcode_from_product_code("12345"))
        self.assertIsNone(barcode_from_product_code("889494"))

    def test_html_helper_ignores_non_product_json_ld(self):
        html = f"""
        <script type="application/ld+json">
        {{"@type":"Organization","name":"Shop","taxID":"{EAN13}"}}
        </script>
        """
        self.assertIsNone(extract_barcode_from_html(html))


class CatalogHealthTests(unittest.TestCase):
    def test_store_floor_warns_below_target_without_failing(self):
        observed = "2026-07-10T12:00:00Z"
        rows = [
            {
                "schemaVersion": 2,
                "country": "uk",
                "retailer": "morrisons",
                "currency": "GBP",
                "c": "Dairy & Eggs",
                "n": "Whole Milk 2 l" if index == 0 else "Loose Bakery Item",
                "p": "1.50",
                "priceType": "regular",
                "ik": f"item-{index}",
                "observedAt": observed,
                **(
                    {
                        "quantity": {
                            "packCount": 1,
                            "itemValue": 2,
                            "itemUnit": "l",
                            "totalValue": 2000,
                            "baseUnit": "ml",
                            "display": "2 l",
                        },
                        "unitPrice": {"value": "0.75", "currency": "GBP", "per": "l"},
                    }
                    if index == 0
                    else {}
                ),
            }
            for index in range(2)
        ]
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps(rows), encoding="utf-8")
            with patch(
                "scripts.catalog_health.store_config",
                return_value={
                    "minimum_products": 1,
                    "optional": False,
                    "minimum_quantity_coverage": 0.40,
                },
            ):
                report = analyze_catalog(
                    "uk",
                    "morrisons",
                    catalog,
                    now=datetime(2026, 7, 10, 13, tzinfo=timezone.utc),
                )

        issue_codes = {issue["code"] for issue in report["issues"]}
        self.assertEqual(report["metrics"]["completeness"]["quantity_coverage"], 0.5)
        self.assertNotIn("quantity_coverage_below_minimum", issue_codes)
        self.assertIn("quantity_coverage_below_target", issue_codes)
        self.assertNotEqual(report["status"], "error")

    def test_contract_compliant_catalog_passes_health_checks(self):
        observed = "2026-07-10T12:00:00Z"
        rows = [
            {
                "schemaVersion": 2,
                "country": "nl",
                "retailer": "aldi",
                "currency": "EUR",
                "c": "Pantry",
                "n": f"Barilla Pasta {index}",
                "p": "1.50",
                "priceType": "regular",
                "ik": f"tok:barilla|pasta-{index}|500g",
                "bn": "barilla",
                "brandSource": "known_name",
                "quantity": {"packCount": 1, "itemValue": 500, "itemUnit": "g", "totalValue": 500, "baseUnit": "g", "display": "500 g"},
                "unitPrice": {"value": "3.00", "currency": "EUR", "per": "kg"},
                "productUrl": f"https://example.test/products/{index}",
                "imageUrl": f"https://example.test/images/{index}.jpg",
                "observedAt": observed,
            }
            for index in range(10)
        ]
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps(rows), encoding="utf-8")
            with patch(
                "scripts.catalog_health.store_config",
                return_value={"minimum_products": 1, "optional": False},
            ):
                report = analyze_catalog(
                    "nl",
                    "aldi",
                    catalog,
                    now=datetime(2026, 7, 10, 13, tzinfo=timezone.utc),
                )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["metrics"]["completeness"]["contract_error_count"], 0)
        self.assertEqual(report["metrics"]["completeness"]["quantity_coverage"], 1.0)
        self.assertEqual(report["metrics"]["completeness"]["category_coverage"], 1.0)

    def test_reports_coverage_duplicates_prices_and_scrape_freshness(self):
        rows = [
            {"n": "One", "p": "1.25", "ik": "one", "b": EAN13, "scraped_at": "2026-07-10T12:00:00Z"},
            {"n": "Two", "p": "999", "ik": "two", "b": EAN13},
            {"n": "Three", "p": "bad", "ik": "two", "b": "123"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps(rows), encoding="utf-8")
            with patch("scripts.catalog_health.store_config", return_value={"minimum_products": 0}):
                report = analyze_catalog(
                    "nl",
                    "aldi",
                    catalog,
                    now=datetime(2026, 7, 10, 13, tzinfo=timezone.utc),
                )

        metrics = report["metrics"]
        self.assertEqual(metrics["product_count"], 3)
        self.assertEqual(metrics["barcode"]["valid_count"], 2)
        self.assertEqual(metrics["barcode"]["invalid_count"], 1)
        self.assertEqual(metrics["barcode"]["duplicate_rows"], 1)
        self.assertEqual(metrics["barcode"]["conflicting_identities"], 1)
        self.assertEqual(metrics["identity"]["duplicate_rows"], 1)
        self.assertEqual(metrics["price"]["invalid_count"], 1)
        self.assertEqual(metrics["price"]["suspicious_count"], 1)
        self.assertEqual(metrics["scrape"]["missing_timestamp_count"], 2)


if __name__ == "__main__":
    unittest.main()
