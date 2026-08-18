from __future__ import annotations

import unittest

from category_utils import infer_category_from_name
from product_sanitize import sanitize_entry_with_reason


class CategoryInferenceTests(unittest.TestCase):
    def test_multilingual_grocery_names_share_one_taxonomy(self):
        cases = {
            "British Whole Milk 2 l": "Dairy & Eggs",
            "Deutsche Hähnchenbrust 500 g": "Meat & Seafood",
            "Nederlandse Aardappelen 1 kg": "Fruits & Vegetables",
            "Tiefkühlpizza Margherita 400 g": "Frozen Foods",
            "Laundry Detergent 30 washes": "Household",
            "Zahnpasta Sensitiv 75 ml": "Personal Care",
        }

        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(infer_category_from_name(name), expected)

    def test_specific_beverage_rule_precedes_chocolate_snack_rule(self):
        self.assertEqual(infer_category_from_name("Chocolate Milk 1 l"), "Beverages")
        self.assertEqual(infer_category_from_name("Milk Chocolate Bar 100 g"), "Snacks")

    def test_german_egg_compounds_do_not_turn_pantry_products_into_dairy(self):
        self.assertEqual(infer_category_from_name("Frische Freilandeier 10 Stück"), "Dairy & Eggs")
        self.assertEqual(infer_category_from_name("Eiernudeln 500 g"), "Pantry")

    def test_sanitizer_upgrades_legacy_other_category(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Deutsche Hähnchenbrust 500 g", "p": "4.99", "s": "500 g", "c": "Other"},
            country="de",
            store="edeka",
            currency="EUR",
        )

        self.assertIsNone(reason)
        self.assertEqual(cleaned["c"], "Meat & Seafood")


if __name__ == "__main__":
    unittest.main()
