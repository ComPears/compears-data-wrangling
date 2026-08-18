import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "countries" / "uk" / "_shared"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SHARED))

from uk_product import parse_gbp_price, raw_product, structure_raw_products  # noqa: E402


class UkProductTests(unittest.TestCase):
    def test_parse_gbp(self):
        self.assertEqual(parse_gbp_price("£1.25"), "1.25")
        self.assertEqual(parse_gbp_price("85p"), "0.85")
        self.assertEqual(parse_gbp_price("2.50"), "2.50")
        self.assertIsNone(parse_gbp_price(""))

    def test_structure(self):
        raw = raw_product(
            name="Tesco Semi Skimmed Milk 2.272L",
            price="£1.65",
            url="/products/1",
            base_url="https://www.tesco.com",
            brand="Tesco",
        )
        raw["sourceQuery"] = "milk"
        raw["sourceMethod"] = "retailer_api"
        self.assertIsNotNone(raw)
        structured = structure_raw_products([raw])
        self.assertEqual(len(structured), 1)
        self.assertEqual(structured[0]["p"], "1.65")
        self.assertTrue(structured[0]["ik"].startswith("tok:"))
        self.assertEqual(structured[0]["brandSource"], "retailer")
        self.assertEqual(structured[0]["sourceQuery"], "milk")
        self.assertEqual(structured[0]["sourceMethod"], "retailer_api")

    def test_multipack_size_is_not_truncated(self):
        structured = structure_raw_products(
            [{"n": "Sparkling Water", "p": "3.60", "s": "6 x 500 ml"}]
        )

        self.assertEqual(structured[0]["s"], "6 × 500 ml")
        self.assertEqual(structured[0]["quantity"]["totalValue"], 3000)


if __name__ == "__main__":
    unittest.main()
