import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "countries" / "uk" / "_shared"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SHARED))

from uk_scrape import (  # noqa: E402
    StoreSearchConfig,
    _walk_for_products,
    harvest_api_json,
    size_from_text_blob,
)


class FakePage:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def evaluate(self, _script, _url):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


CFG = StoreSearchConfig(
    slug="test-store",
    base_url="https://example.com",
    search_url=lambda query: f"https://example.com/search?q={query}",
    api_url=lambda query: f"https://example.com/api?q={query}",
    card_selectors=("article",),
)


class UkScrapeApiTests(unittest.TestCase):
    def test_extracts_package_size_but_not_unit_price(self):
        self.assertEqual(
            size_from_text_blob("Morrisons Whole Milk\n2 litres\n£1.65\n82.5p / litre"),
            "2 litres",
        )
        self.assertIsNone(size_from_text_blob("£3.20\nPrice per kg £8.00"))

    def test_offer_price_wins_over_unit_price(self):
        found = []

        _walk_for_products(
            {
                "name": "Herbal Tea 20 Bags",
                "pricePerUnit": 166.67,
                "sellingPrice": 2.50,
                "url": "/product/tea",
                "brand": {"name": "Pukka"},
                "id": "tea-20",
            },
            found,
            CFG,
        )

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["p"], "2.50")
        self.assertEqual(found[0]["bn"], "Pukka")
        self.assertEqual(found[0]["brandSource"], "retailer")
        self.assertEqual(found[0]["retailerProductId"], "tea-20")

    def test_api_package_size_fields_are_preserved(self):
        found = []

        _walk_for_products(
            {
                "name": "Whole Milk",
                "sellingPrice": 1.65,
                "packageSize": {"value": 2, "unit": "l"},
                "url": "/product/milk",
            },
            found,
            CFG,
        )

        self.assertEqual(found[0]["s"], "2 l")

    def test_does_not_retry_a_persistent_403(self):
        page = FakePage([{"ok": False, "status": 403, "text": "blocked"}])

        result = harvest_api_json(page, CFG, "milk")

        self.assertEqual(result.status, 403)
        self.assertEqual(result.products, [])
        self.assertEqual(page.calls, 1)

    @patch("uk_scrape.time.sleep", return_value=None)
    @patch("uk_scrape.random.uniform", return_value=0)
    def test_retries_transient_api_failures(self, _random, _sleep):
        product_payload = {
            "products": [
                {
                    "name": "Example Milk 1L",
                    "price": {"price": "1.25"},
                    "url": "/product/milk",
                }
            ]
        }
        page = FakePage(
            [
                {"ok": False, "status": 503, "text": "busy"},
                {"ok": True, "status": 200, "text": json.dumps(product_payload)},
            ]
        )

        result = harvest_api_json(page, CFG, "milk")

        self.assertEqual(result.status, 200)
        self.assertEqual(len(result.products), 1)
        self.assertEqual(page.calls, 2)


if __name__ == "__main__":
    unittest.main()
