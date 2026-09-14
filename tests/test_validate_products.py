import unittest

from config.paths import store_config
from scripts.validate_products import quantity_coverage_messages


class QuantityCoverageGateTests(unittest.TestCase):
    def report(self, country: str, store: str, coverage: float) -> dict:
        return {
            "country": country,
            "store": store,
            "total": 1_000,
            "with_quantity": round(coverage * 1_000),
        }

    def test_recent_lidl_variance_warns_without_rejecting_valid_catalogs(self):
        observed_coverages = {
            ("nl", "lidl"): 0.213,
            ("de", "lidl-de"): 0.216,
        }

        for (country, store), coverage in observed_coverages.items():
            with self.subTest(country=country, store=store):
                failure, warning = quantity_coverage_messages(
                    self.report(country, store, coverage),
                    store_config(country, store),
                )
                self.assertIsNone(failure)
                self.assertIn("below target", warning or "")

    def test_catastrophic_quantity_regression_still_fails(self):
        failure, warning = quantity_coverage_messages(
            self.report("nl", "lidl", 0.10),
            store_config("nl", "lidl"),
        )

        self.assertIn("below hard floor", failure or "")
        self.assertIsNone(warning)

    def test_invalid_threshold_order_fails_configuration(self):
        failure, warning = quantity_coverage_messages(
            self.report("nl", "lidl", 0.50),
            {"minimum_quantity_coverage": 0.60, "target_quantity_coverage": 0.50},
        )

        self.assertIn("invalid quantity coverage thresholds", failure or "")
        self.assertIsNone(warning)

    def test_actual_sainsburys_boundary_failure_is_not_rounded_away(self):
        failure, warning = quantity_coverage_messages(
            {"country": "uk", "store": "sainsburys", "total": 2278, "with_quantity": 2050},
            {"minimum_quantity_coverage": 0.90, "target_quantity_coverage": 0.90},
        )
        self.assertIn("89.9912% below hard floor 90.0000%", failure)
        self.assertIn("2050/2278 products", failure)
        self.assertIsNone(warning)

    def test_exact_floor_and_one_more_observed_quantity_pass(self):
        for total, count in ((100, 90), (2278, 2051)):
            with self.subTest(total=total, count=count):
                self.assertEqual(quantity_coverage_messages(
                    {"country": "uk", "store": "sainsburys", "total": total, "with_quantity": count},
                    {"minimum_quantity_coverage": 0.90, "target_quantity_coverage": 0.90},
                ), (None, None))


if __name__ == "__main__":
    unittest.main()
