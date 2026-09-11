import json
import importlib.util
import sys
import unittest
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "countries/uk/_shared"))
from uk_product import structure_raw_products
from lidl_products import product_from_tile
from product_sanitize import sanitize_entry_with_reason


def tile(**metadata):
    return {
        "metadata": quote(json.dumps({
            "id": "10054607", "name": "Original Drink", "brand": "HATA RAMUNE",
            "category": "Food", "price": 1.69, **metadata,
        })),
        "href": "https://www.lidl.co.uk/p/hata-ramune-original-drink/p10054607#searchTrackingQuery=milk",
        "text": "Original Drink for 1.69\nWith Lidl Plus\nSAVE £0.20\n£1.69\nRegular price £1.89\n£8.45/l",
        "availability": "In store from 17.09",
        "image": "https://imgproxy-retcat.assets.schwarz/product.jpg",
    }


class LidlProductTests(unittest.TestCase):
    def test_lidl_uses_80_unique_grocery_queries(self):
        spec = importlib.util.spec_from_file_location(
            "lidl_main", Path(__file__).resolve().parents[1] / "countries/uk/lidl-uk/main.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(len(module.LIDL_QUERIES), 80)
        self.assertEqual(len(set(module.LIDL_QUERIES)), 80)
        self.assertTrue({"milk", "bread", "nuts", "wine"}.issubset(module.LIDL_QUERIES))
        self.assertFalse(module.NON_FOOD_QUERIES.intersection(module.LIDL_QUERIES))

    def test_uses_metadata_not_saving_unit_price_or_accessibility_title(self):
        row = product_from_tile(tile())
        self.assertEqual(row["p"], "1.69")
        self.assertEqual(row["n"], "Original Drink")
        self.assertEqual(row["retailerProductId"], "10054607")
        self.assertNotIn("#", row["productUrl"])
        self.assertEqual(row["s"], "")
        self.assertEqual(row["bn"], "HATA RAMUNE")
        self.assertEqual(row["availability"], "preorder")

    def test_food_evidence_survives_full_structure_and_sanitize(self):
        row = structure_raw_products([product_from_tile(tile())])[0]
        cleaned, reason = sanitize_entry_with_reason(row, country="uk", store="lidl-uk")
        self.assertIsNone(reason)
        self.assertEqual(cleaned["retailerCategory"], "Food")
        self.assertEqual(cleaned["priceType"], "loyalty")
        self.assertEqual(cleaned["availabilityText"], "In store from 17.09")
        self.assertNotIn("quantity", cleaned)

    def test_nonfood_is_rejected_even_with_food_word_and_quantity(self):
        self.assertIsNone(product_from_tile(tile(name="Assorted Wing Nuts - 76 Pieces", category="NonFood")))

    def test_unknown_categories_are_not_assumed_food(self):
        for category in (None, "", "Other", "food", "Food/Unknown"):
            with self.subTest(category=category):
                self.assertIsNone(product_from_tile(tile(category=category)))

    def test_missing_or_malformed_metadata_does_not_fall_back_to_text(self):
        for data in ("", "not-json", "null", "[]"):
            sample = tile()
            sample["metadata"] = data
            self.assertIsNone(product_from_tile(sample))

    def test_bad_prices_and_mismatched_identity_are_rejected(self):
        for price in (True, None, "1.69", 0, -1, float("nan"), float("inf")):
            self.assertIsNone(product_from_tile(tile(price=price)))
        self.assertIsNone(product_from_tile(tile(id="999")))
        sample = tile()
        sample["href"] = "https://example.com/p/product/p10054607"
        self.assertIsNone(product_from_tile(sample))

    def test_explicit_title_pack_size_is_preserved(self):
        row = product_from_tile(tile(name="Milk Chocolate Wafer Creams 8 Pack"))
        self.assertEqual(row["s"], "8 items")

    def test_multibuy_total_is_not_a_single_item_price(self):
        sample = tile(name="Premium Macaroni", price=6)
        sample["text"] = "With Lidl Plus\n2 for\n£6.00\nRegular price £3.29"
        row = product_from_tile(sample)
        self.assertEqual(row["p"], "3.29")
        self.assertEqual(row["o"], "")
        sample["text"] = "With Lidl Plus\n2 for\n£6.00"
        self.assertIsNone(product_from_tile(sample))

    def test_unverified_food_labels_do_not_bypass_quarantine(self):
        for source in (None, "search_query", "unknown"):
            row = product_from_tile(tile())
            row["categorySource"] = source
            cleaned, reason = sanitize_entry_with_reason(row, country="uk", store="lidl-uk")
            self.assertIsNone(cleaned)
            self.assertEqual(reason, "ambiguous_lidl_non_grocery")

    def test_explicit_durable_filter_still_applies(self):
        row = product_from_tile(tile(name="Coffee Machine"))
        cleaned, reason = sanitize_entry_with_reason(row, country="uk", store="lidl-uk")
        self.assertIsNone(cleaned)
        self.assertEqual(reason, "durable_non_grocery")


if __name__ == "__main__":
    unittest.main()
