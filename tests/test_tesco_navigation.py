import unittest
from unittest.mock import MagicMock, patch
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from countries.uk.tesco.main import CFG, navigate_tesco_search
from uk_scrape import same_search_location


class TescoNavigationTests(unittest.TestCase):
    def test_form_search_keeps_the_warmed_page(self):
        self.assertTrue(CFG.reuse_page)
        self.assertIs(CFG.navigate_search, navigate_tesco_search)

    def test_query_encoding_is_compared_semantically(self):
        self.assertTrue(same_search_location(CFG.search_url("whole milk"), "https://www.tesco.com/shop/en-GB/search?query=whole%20milk"))
        self.assertFalse(same_search_location(CFG.base_url, CFG.search_url("milk")))
        self.assertTrue(same_search_location(CFG.search_url("milk") + "&inputType=free_text", CFG.search_url("milk")))
        self.assertFalse(same_search_location(CFG.search_url("bread") + "&inputType=free_text", CFG.search_url("milk")))

    def test_submits_search_form_and_waits_for_matching_url_and_heading(self):
        page = MagicMock()
        navigate_tesco_search(page, "semi skimmed milk")
        page.locator.assert_called_once_with('input[type="search"]')
        page.locator.return_value.first.fill.assert_called_once_with("semi skimmed milk", timeout=15000)
        page.locator.return_value.first.press.assert_called_once_with("Enter")
        page.goto.assert_not_called()
        matches_url = page.wait_for_url.call_args.args[0]
        self.assertTrue(matches_url("https://www.tesco.com/shop/en-GB/search?query=semi%20skimmed%20milk"))
        self.assertTrue(matches_url("https://www.tesco.com/shop/en-GB/search?query=semi+skimmed+milk"))
        self.assertFalse(matches_url("https://www.tesco.com/shop/en-GB/search?query=milk"))
        heading = page.get_by_role.call_args.kwargs["name"]
        self.assertTrue(heading.fullmatch('Results for “semi skimmed milk”'))
        self.assertFalse(heading.fullmatch('Results for “milk”'))
        page.get_by_role.return_value.wait_for.assert_called_once_with(state="visible", timeout=30000)

    def test_alternate_results_heading_and_regex_characters(self):
        page = MagicMock()
        navigate_tesco_search(page, "milk (whole)")
        heading = page.get_by_role.call_args.kwargs["name"]
        self.assertTrue(heading.fullmatch('Products we\'ve found for “milk (whole)”'))
        self.assertTrue(heading.fullmatch('Products we’ve found for "milk (whole)"'))
        self.assertFalse(heading.fullmatch('Products we\'ve found for “milk whole”'))

    @patch("countries.uk.tesco.main.accept_uk_cookies")
    @patch("countries.uk.tesco.main.goto_resilient")
    @patch("countries.uk.tesco.main.search_page_state", return_value="unclassified_empty")
    def test_stalled_form_gets_one_homepage_recovery(self, _state, goto, consent):
        page = MagicMock()
        page.locator.return_value.first.fill.side_effect = [PlaywrightTimeoutError("Locator.fill"), None]
        navigate_tesco_search(page, "milk")
        goto.assert_called_once_with(page, CFG.warm_url, timeout=45000, retries=1)
        consent.assert_called_once_with(page)
        self.assertEqual(page.locator.return_value.first.fill.call_count, 2)

    @patch("countries.uk.tesco.main.goto_resilient")
    @patch("countries.uk.tesco.main.search_page_state", return_value="blocked")
    def test_explicit_block_is_not_retried(self, _state, goto):
        page = MagicMock()
        page.locator.return_value.first.fill.side_effect = PlaywrightTimeoutError("Locator.fill")
        with self.assertRaises(PlaywrightTimeoutError):
            navigate_tesco_search(page, "milk")
        goto.assert_not_called()

    @patch("countries.uk.tesco.main.accept_uk_cookies")
    @patch("countries.uk.tesco.main.goto_resilient")
    @patch("countries.uk.tesco.main.search_page_state", return_value="unclassified_empty")
    def test_second_timeout_is_not_hidden(self, _state, goto, _consent):
        page = MagicMock()
        page.locator.return_value.first.fill.side_effect = PlaywrightTimeoutError("Locator.fill")
        with self.assertRaises(PlaywrightTimeoutError):
            navigate_tesco_search(page, "milk")
        self.assertEqual(page.locator.return_value.first.fill.call_count, 2)
        goto.assert_called_once()

    @patch("countries.uk.tesco.main.accept_uk_cookies")
    @patch("countries.uk.tesco.main.goto_resilient")
    @patch("countries.uk.tesco.main.search_page_state", side_effect=["unclassified_empty", "blocked"])
    def test_blocked_homepage_stops_recovery(self, _state, _goto, consent):
        page = MagicMock()
        page.locator.return_value.first.fill.side_effect = PlaywrightTimeoutError("Locator.fill")
        with self.assertRaises(PlaywrightTimeoutError):
            navigate_tesco_search(page, "milk")
        self.assertEqual(page.locator.return_value.first.fill.call_count, 1)
        consent.assert_not_called()
