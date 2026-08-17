from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "countries" / "de" / "_shared"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SHARED))

from de_product import parse_eur_price, raw_product, structure_raw_products  # noqa: E402


class DeProductTests(unittest.TestCase):
    def test_parses_localized_euro_price(self):
        self.assertEqual(parse_eur_price("1,29 €"), "1.29")
        self.assertEqual(parse_eur_price("€ 1.234,56"), "1234.56")
        self.assertIsNone(parse_eur_price("kostenlos"))

    def test_structure_preserves_retailer_metadata_and_mass(self):
        raw = raw_product(
            name="Milsani Frische Vollmilch 3,5 % 1 L",
            price="1,19 €",
            url="/produkt/milch-1",
            image="/images/milch.jpg",
            base_url="https://example.de",
            retailer_product_id="milk-1",
            brand="Milsani",
        )
        raw["sourceQuery"] = "Milch"
        raw["sourceMethod"] = "retailer_api"

        rows = structure_raw_products([raw])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["p"], "1.19")
        self.assertEqual(rows[0]["c"], "Dairy & Eggs")
        self.assertEqual(rows[0]["retailerProductId"], "milk-1")
        self.assertEqual(rows[0]["brandSource"], "retailer")
        self.assertEqual(rows[0]["quantity"]["baseUnit"], "ml")
        self.assertEqual(rows[0]["productUrl"], "https://example.de/produkt/milch-1")
        self.assertEqual(rows[0]["sourceQuery"], "Milch")

    def test_multipack_size_is_not_truncated(self):
        rows = structure_raw_products(
            [{"n": "Mineralwasser", "p": "3,60", "s": "6 x 500 ml"}]
        )

        self.assertEqual(rows[0]["s"], "6 × 500 ml")
        self.assertEqual(rows[0]["quantity"]["totalValue"], 3000)


if __name__ == "__main__":
    unittest.main()
