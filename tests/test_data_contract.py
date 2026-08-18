from __future__ import annotations

import unittest

from data_contract import is_valid_quantity, normalize_price, parse_quantity, quantity_fingerprint, unit_price
from product_sanitize import sanitize_entry_with_reason


class DataContractTests(unittest.TestCase):
    def test_mass_and_volume_keep_distinct_units(self):
        mass = parse_quantity("400 g")
        volume = parse_quantity("1 l")

        self.assertEqual(mass["totalValue"], 400)
        self.assertEqual(mass["baseUnit"], "g")
        self.assertEqual(mass["display"], "400 g")
        self.assertEqual(volume["totalValue"], 1000)
        self.assertEqual(volume["baseUnit"], "ml")
        self.assertEqual(volume["display"], "1 l")
        self.assertNotEqual(quantity_fingerprint(mass), quantity_fingerprint(volume))

    def test_multipack_preserves_pack_shape_and_total(self):
        quantity = parse_quantity("6 x 330 ml")

        self.assertEqual(quantity["packCount"], 6)
        self.assertEqual(quantity["itemValue"], 330)
        self.assertEqual(quantity["totalValue"], 1980)
        self.assertEqual(quantity_fingerprint(quantity), "6x330ml")
        self.assertEqual(
            unit_price("5.94", "EUR", quantity),
            {"value": "3.00", "currency": "EUR", "per": "l"},
        )
        self.assertTrue(is_valid_quantity(quantity))

    def test_invalid_existing_quantity_is_reparsed_instead_of_trusted(self):
        quantity = parse_quantity(
            "500 g",
            existing={
                "packCount": 1,
                "itemValue": 500,
                "itemUnit": "ml",
                "totalValue": 500,
                "baseUnit": "g",
            },
        )

        self.assertEqual(quantity["itemUnit"], "g")
        self.assertTrue(is_valid_quantity(quantity))

    def test_zero_placeholder_size_falls_back_to_product_name(self):
        quantity = parse_quantity("0 ml", name="Apple Juice 1 litre")

        self.assertEqual(quantity["totalValue"], 1000)
        self.assertEqual(quantity["baseUnit"], "ml")

    def test_count_quantity_supports_localized_label(self):
        quantity = parse_quantity("10 stuks")

        self.assertEqual(quantity["packCount"], 10)
        self.assertEqual(quantity["baseUnit"], "count")
        self.assertEqual(quantity["display"], "10 items")
        self.assertEqual(parse_quantity("6 Stück")["totalValue"], 6)
        self.assertEqual(parse_quantity("20 bags")["totalValue"], 20)
        self.assertEqual(parse_quantity("24 tablets")["display"], "24 items")

    def test_uk_imperial_units_are_converted_to_comparable_base_units(self):
        ounces = parse_quantity("12 oz")
        pints = parse_quantity("4 pints")

        self.assertAlmostEqual(ounces["totalValue"], 340.194278, places=5)
        self.assertEqual(ounces["baseUnit"], "g")
        self.assertAlmostEqual(pints["totalValue"], 2273.045, places=6)
        self.assertEqual(pints["baseUnit"], "ml")

    def test_price_normalization_rejects_invalid_and_implausible_values(self):
        self.assertEqual(normalize_price("€ 1,29"), ("1.29", None))
        self.assertEqual(normalize_price("£1,299.99"), (None, "implausible_price"))
        self.assertEqual(normalize_price("0"), (None, "invalid_price"))
        self.assertEqual(normalize_price("free"), (None, "invalid_price"))

    def test_sanitizer_emits_versioned_offer_contract(self):
        cleaned, reason = sanitize_entry_with_reason(
            {
                "n": "Barilla Spaghetti 400 g",
                "p": "1,60",
                "s": "400 g",
                "bn": "Barilla",
                "url": "https://example.test/products/spaghetti",
                "image": "https://example.test/images/spaghetti.jpg",
            },
            country="nl",
            store="example",
            currency="EUR",
            observed_at="2026-08-17T12:00:00Z",
        )

        self.assertIsNone(reason)
        self.assertEqual(cleaned["schemaVersion"], 2)
        self.assertEqual(cleaned["country"], "nl")
        self.assertEqual(cleaned["retailer"], "example")
        self.assertEqual(cleaned["currency"], "EUR")
        self.assertEqual(cleaned["priceType"], "regular")
        self.assertEqual(cleaned["quantity"]["baseUnit"], "g")
        self.assertEqual(cleaned["brandSource"], "known_name")
        self.assertEqual(cleaned["wu"], "g")
        self.assertEqual(cleaned["unitPrice"]["value"], "4.00")
        self.assertEqual(cleaned["unitPrice"]["per"], "kg")
        self.assertEqual(cleaned["observedAt"], "2026-08-17T12:00:00+00:00")
        self.assertEqual(cleaned["productUrl"], "https://example.test/products/spaghetti")
        self.assertEqual(cleaned["imageUrl"], "https://example.test/images/spaghetti.jpg")
        self.assertTrue(cleaned["ik"].endswith("|400g"))

    def test_sanitizer_returns_machine_readable_quarantine_reason(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Milk 1 l", "p": "0", "s": "1 l"},
            country="uk",
            store="example",
        )

        self.assertIsNone(cleaned)
        self.assertEqual(reason, "invalid_price")

    def test_invalid_explicit_urls_are_removed(self):
        cleaned, reason = sanitize_entry_with_reason(
            {
                "n": "Whole Milk 1 l",
                "p": "1.25",
                "s": "1 l",
                "productUrl": "javascript:alert(1)",
                "imageUrl": "not-a-url",
            },
            country="uk",
            store="tesco",
            currency="GBP",
        )

        self.assertIsNone(reason)
        self.assertNotIn("productUrl", cleaned)
        self.assertNotIn("imageUrl", cleaned)

    def test_uk_offer_price_ceiling_rejects_accidentally_selected_unit_prices(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Herbal Tea 20 bags", "p": "166.67", "s": "20 pack"},
            country="uk",
            store="morrisons",
            currency="GBP",
        )

        self.assertIsNone(cleaned)
        self.assertEqual(reason, "implausible_price")

    def test_loyalty_price_is_explicitly_labelled(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Cravendale Milk 2 l", "p": "2.00", "s": "2 l", "o": "£2 Clubcard Price"},
            country="uk",
            store="tesco",
            currency="GBP",
        )

        self.assertIsNone(reason)
        self.assertEqual(cleaned["priceType"], "loyalty")

    def test_durable_goods_leaked_by_supermarket_search_are_quarantined(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Silvercrest Coffee Machine 1.2 l", "p": "39.99", "s": "1.2 l"},
            country="uk",
            store="lidl-uk",
        )

        self.assertIsNone(cleaned)
        self.assertEqual(reason, "durable_non_grocery")

    def test_lidl_rows_without_package_evidence_are_quarantined(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Seasonal Special Collection", "p": "12.99", "c": "Other"},
            country="uk",
            store="lidl-uk",
            currency="GBP",
        )

        self.assertIsNone(cleaned)
        self.assertEqual(reason, "ambiguous_lidl_non_grocery")

    def test_lidl_grocery_with_package_evidence_is_kept(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Chocolate Biscuits 300 g", "p": "1.99", "c": "Snacks"},
            country="uk",
            store="lidl-uk",
            currency="GBP",
        )

        self.assertIsNone(reason)
        self.assertEqual(cleaned["quantity"]["display"], "300 g")

    def test_ambiguous_rule_is_not_applied_to_other_retailers(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Seasonal Special Collection", "p": "2.99", "c": "Other"},
            country="uk",
            store="tesco",
            currency="GBP",
        )

        self.assertIsNone(reason)
        self.assertIsNotNone(cleaned)

    def test_generic_product_name_is_not_mistaken_for_a_brand(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Semi Skimmed Milk 2 l", "p": "1.50", "s": "2 l"},
            country="uk",
            store="tesco",
            currency="GBP",
        )

        self.assertIsNone(reason)
        self.assertNotIn("bn", cleaned)

    def test_multiword_brand_is_canonical_but_component_words_are_not_brands(self):
        branded, branded_reason = sanitize_entry_with_reason(
            {"n": "Coca-Cola Zero 1 l", "p": "1.99", "s": "1 l"}
        )
        generic, generic_reason = sanitize_entry_with_reason(
            {"n": "Red Apples 1 kg", "p": "2.49", "s": "1 kg"}
        )

        self.assertIsNone(branded_reason)
        self.assertIsNone(generic_reason)
        self.assertEqual(branded["bn"], "coca-cola")
        self.assertEqual(branded["brandSource"], "known_name")
        self.assertNotIn("bn", generic)

    def test_unproven_legacy_brand_is_removed_before_matching(self):
        cleaned, reason = sanitize_entry_with_reason(
            {"n": "Semi Skimmed Milk 2 l", "p": "1.50", "s": "2 l", "bn": "semi"},
            country="uk",
            store="tesco",
            currency="GBP",
        )

        self.assertIsNone(reason)
        self.assertNotIn("bn", cleaned)
        self.assertTrue(cleaned["ik"].startswith("tok:unknown|"))


if __name__ == "__main__":
    unittest.main()
