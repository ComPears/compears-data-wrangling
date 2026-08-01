import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "countries" / "uk" / "_shared"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SHARED))

from uk_scrape import StoreSearchConfig, harvest_api_json  # noqa: E402


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
