from __future__ import annotations

import unittest

from data_contract import parse_quantity
from product_matching import canonical_product_id, score_match


def offer(*, brand: str, name: str, size: str, barcode: str | None = None) -> dict:
    row = {
        "bn": brand,
        "brandSource": "retailer",
        "cn": name,
        "quantity": parse_quantity(size),
    }
    if barcode:
        row["b"] = barcode
    return row


class ProductMatchingTests(unittest.TestCase):
    def test_exact_gtin_is_an_automatic_match(self):
        left = offer(brand="Barilla", name="barilla spaghetti", size="500 g", barcode="8076800195057")
        right = offer(brand="Barilla", name="barilla spaghetti no 5", size="500 g", barcode="8076800195057")

        decision = score_match(left, right)

        self.assertEqual(decision.method, "gtin")
        self.assertEqual(decision.confidence, 1.0)
        self.assertTrue(decision.auto_match)

    def test_same_attributes_are_an_automatic_match(self):
        left = offer(brand="Barilla", name="barilla spaghetti no 5", size="500 g")
        right = offer(brand="barilla", name="Spaghetti No 5 Barilla", size="500g")

        decision = score_match(left, right)

        self.assertEqual(decision.method, "normalized_attributes")
        self.assertTrue(decision.auto_match)
        self.assertGreaterEqual(decision.confidence, 0.95)

    def test_different_package_size_is_never_auto_matched(self):
        left = offer(brand="Barilla", name="barilla spaghetti", size="400 g")
        right = offer(brand="Barilla", name="barilla spaghetti", size="500 g")

        decision = score_match(left, right)

        self.assertEqual(decision.method, "none")
        self.assertFalse(decision.auto_match)
        self.assertEqual(decision.reason, "package quantity differs")

    def test_ambiguous_variant_is_review_only(self):
        left = offer(
            brand="Coca Cola",
            name="coca cola zero sugar cherry sparkling soft drink bottle",
            size="1.5 l",
        )
        right = offer(
            brand="Coca Cola",
            name="coca cola zero sugar vanilla sparkling soft drink bottle",
            size="1.5 l",
        )

        decision = score_match(left, right)

        self.assertEqual(decision.method, "review")
        self.assertFalse(decision.auto_match)

    def test_different_gtins_override_similar_names(self):
        left = offer(brand="Barilla", name="barilla spaghetti", size="500 g", barcode="8076800195057")
        right = offer(brand="Barilla", name="barilla spaghetti", size="500 g", barcode="8076802085738")

        decision = score_match(left, right)

        self.assertEqual(decision.confidence, 0.0)
        self.assertFalse(decision.auto_match)

    def test_canonical_id_is_stable_and_country_scoped(self):
        self.assertEqual(canonical_product_id("nl", "ean:123"), canonical_product_id("nl", "ean:123"))
        self.assertNotEqual(canonical_product_id("nl", "ean:123"), canonical_product_id("uk", "ean:123"))


if __name__ == "__main__":
    unittest.main()
