import json
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from countries.uk.tesco.main import CFG
from uk_scrape import scrape_store_search, search_page_state, write_search_diagnostics


class SearchSessionTests(unittest.TestCase):
    def run_search(self, batches, *, statuses=None, reuse=True, form=False, authoritative=False, redirected=False):
        page = MagicMock()
        page.url = CFG.base_url
        page.title.return_value = "Search"
        page.locator.return_value.inner_text.return_value = "Products"
        listeners = []
        page.on.side_effect = lambda event, handler: listeners.append(handler)
        page.remove_listener.side_effect = lambda event, handler: listeners.remove(handler)
        browser = MagicMock()
        browser.new_context.return_value.new_page.return_value = page
        navigations = []
        listener_counts = []

        def navigate(_page, url, **kwargs):
            page.url = CFG.base_url if redirected else url
            navigations.append(url)
            listener_counts.append(len(listeners))
            status = 200 if len(navigations) == 1 else (statuses or [200] * len(batches))[len(navigations) - 2]
            response = MagicMock()
            response.status = status
            response.frame = page.main_frame
            response.request.is_navigation_request.return_value = True
            response.json.side_effect = ValueError("not JSON")
            response.headers = {}
            response.url = url
            for handler in list(listeners):
                handler(response)

        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(patch("builtins.print"))
            stack.enter_context(patch.dict("os.environ", {
                "UK_MAX_QUERIES": "80", "UK_MAX_EMPTY_QUERIES": "5",
                "UK_MAX_BLOCKED_QUERIES": "3", "UK_DIAGNOSTICS_DIR": directory,
            }))
            stack.enter_context(patch("uk_scrape.launch_browser", return_value=browser))
            goto = stack.enter_context(patch("uk_scrape.goto_resilient", side_effect=navigate))
            consent = stack.enter_context(patch("uk_scrape.accept_uk_cookies"))
            stack.enter_context(patch("uk_scrape.configure_page"))
            stack.enter_context(patch("uk_scrape.time.sleep"))
            cards = stack.enter_context(patch("uk_scrape.extract_from_cards", side_effect=batches))
            stack.enter_context(patch("uk_scrape.extract_json_ld", return_value=[]))
            extractor = MagicMock(side_effect=batches) if authoritative else None
            result = scrape_store_search(
                MagicMock(), replace(CFG, reuse_page=reuse, extract_products=extractor, navigate_search=(lambda page, query: navigate(page, CFG.search_url(query))) if form else None), Path(directory) / "products.json",
                queries=[f"query-{i}" for i in range(len(batches))],
            )
            diagnostics = json.loads((Path(directory) / "tesco-search.json").read_text())
            if authoritative:
                cards.assert_not_called()
            if form:
                self.assertEqual(goto.call_count, 1)  # homepage only
                self.assertEqual(consent.call_count, 2)  # both before any search
        self.assertEqual(listeners, [])
        browser.close.assert_called_once()
        return result, diagnostics, browser, listener_counts

    def test_all_80_queries_reuse_warmed_tab_without_accumulating_listeners(self):
        batches = [[{"n": f"Milk {i}", "i": f"product-{i}", "p": "1.00"}] for i in range(80)]
        result, diagnostics, browser, listeners = self.run_search(batches)
        self.assertEqual(len(result), 80)
        self.assertEqual(len(diagnostics["queries"]), 80)
        browser.new_context.return_value.new_page.assert_called_once()
        self.assertEqual(listeners, [0] + [3] * 80)
        self.assertEqual(result[-1]["sourceQuery"], "query-79")

    def test_dom_403s_stop_at_blocked_limit_not_empty_limit(self):
        result, diagnostics, _, _ = self.run_search([[]] * 5, statuses=[403] * 5)
        self.assertEqual(result, [])
        self.assertEqual(len(diagnostics["queries"]), 3)
        self.assertTrue(all(row["state"] == "blocked" for row in diagnostics["queries"]))

    def test_empty_query_does_not_reuse_previous_batch(self):
        result, diagnostics, _, _ = self.run_search([[{"n": "Milk", "i": "milk"}], [], [{"n": "Bread", "i": "bread"}]])
        self.assertEqual(len(result), 2)
        self.assertEqual([row["batch_count"] for row in diagnostics["queries"]], [1, 0, 1])

    def test_blocked_document_cannot_publish_captured_products(self):
        result, diagnostics, _, _ = self.run_search([[{"n": "Milk", "i": "milk"}]], statuses=[403])
        self.assertEqual(result, [])
        self.assertEqual(diagnostics["queries"][0]["state"], "blocked")

    def test_exception_is_diagnosed_and_listener_cleanup_continues(self):
        _, diagnostics, _, counts = self.run_search([RuntimeError("sensitive detail"), []])
        self.assertEqual(diagnostics["queries"][0]["error_type"], "RuntimeError")
        self.assertNotIn("sensitive detail", json.dumps(diagnostics))
        self.assertEqual(counts, [0, 3, 3])

    def test_non_sticky_stores_still_use_separate_pages(self):
        _, _, browser, _ = self.run_search([[], []], reuse=False)
        self.assertEqual(browser.new_context.return_value.new_page.call_count, 3)

    def test_authoritative_parser_never_falls_back_to_generic_guesses(self):
        result, diagnostics, _, _ = self.run_search(
            [[{"n": "Original Drink", "i": "drink", "p": "1.69"}], []],
            authoritative=True,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(diagnostics["queries"][0]["source_method"], "retailer_product_grid")
        self.assertEqual(diagnostics["queries"][1]["batch_count"], 0)

    def test_authoritative_parser_rejects_redirected_search(self):
        result, diagnostics, _, _ = self.run_search(
            [[{"n": "Original Drink", "i": "drink", "p": "1.69"}]],
            authoritative=True, redirected=True,
        )
        self.assertEqual(result, [])
        self.assertFalse(diagnostics["queries"][0]["expected_location"])
        self.assertEqual(diagnostics["queries"][0]["error_type"], "RuntimeError")

    def test_form_navigation_does_not_reload_or_accept_cookies_on_result_pages(self):
        result, diagnostics, browser, _ = self.run_search(
            [[{"n": "Milk", "i": "milk"}], [{"n": "Bread", "i": "bread"}]], form=True,
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(all(row["expected_location"] for row in diagnostics["queries"]))
        browser.new_context.return_value.new_page.assert_called_once()


class SearchDiagnosticTests(unittest.TestCase):
    def test_classifies_public_failure_signals(self):
        page = MagicMock()
        page.title.return_value = "Search"
        for status, body, expected in [
            (200, "Access Denied", "blocked"),
            (429, "", "blocked"),
            (503, "Try later", "server_error"),
            (404, "Missing", "http_error"),
            (200, "No products found", "no_results"),
            (200, "Loading", "unclassified_empty"),
        ]:
            page.locator.return_value.inner_text.return_value = body
            self.assertEqual(search_page_state(page, status), expected)

    def test_diagnostics_are_written_even_before_first_query(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"UK_DIAGNOSTICS_DIR": directory}):
            write_search_diagnostics(Path(directory) / "products.json", CFG, [])
            data = json.loads((Path(directory) / "tesco-search.json").read_text())
            self.assertEqual(data["queries"], [])


if __name__ == "__main__":
    unittest.main()
