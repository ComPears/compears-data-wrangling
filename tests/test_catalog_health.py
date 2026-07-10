from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ah_api_client import product_to_raw_entry
from barcode_utils import extract_barcode_from_entry, normalize_barcode
from dirk_barcode import extract_card_barcode
from plus_scrape import _product_from_plp
from scripts.catalog_health import analyze_catalog


EAN13 = "4006381333931"
EAN8 = "96385074"


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

    def test_dirk_reads_data_attribute_or_product_json_ld(self):
        self.assertEqual(extract_card_barcode(FakeCard({"data-ean": EAN13})), EAN13)
        card = FakeCard(scripts=[FakeScript(json.dumps({"@type": "Product", "gtin8": EAN8}))])
        self.assertEqual(extract_card_barcode(card), EAN8)


class CatalogHealthTests(unittest.TestCase):
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
