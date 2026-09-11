import unittest

from scripts.verify_tesco_refresh import refresh_failures


class FullRefreshTests(unittest.TestCase):
    def test_single_query_is_not_a_full_run(self):
        self.assertTrue(refresh_failures({"outcome": "refreshed"}, {"queries": [{"state": "products"}]}))

    def test_preserved_data_is_not_success_even_with_80_queries(self):
        self.assertTrue(refresh_failures({"outcome": "preserved"}, {"queries": [{"state": "products"}] * 80}))

    def test_blocked_queries_fail_even_above_product_minimum(self):
        self.assertTrue(refresh_failures({"outcome": "refreshed"}, {"queries": [{"state": "products"}] * 79 + [{"state": "blocked"}]}))

    def test_complete_success_can_include_genuine_empty_results(self):
        self.assertEqual(refresh_failures({"outcome": "refreshed"}, {"queries": [{"state": "products"}] * 79 + [{"state": "no_results"}]}), [])

    def test_redirect_does_not_count_as_search_success(self):
        self.assertTrue(refresh_failures({"outcome": "refreshed"}, {"queries": [{"state": "products", "expected_location": False}] * 80}))
