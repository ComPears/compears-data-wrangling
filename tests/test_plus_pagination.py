import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import plus_scrape as plus
from scripts.verify_plus_refresh import refresh_failures


URL = "https://www.plus.nl/producten/baby-drogisterij"


def payload(ids, pages=2, total=3):
    return {"TotalPages": pages, "TotalNumberItems": total,
            "ProductList": {"List": [{"PLP_Str": {"Name": f"Item {i}",
                "Slug": str(i), "OriginalPrice": "2.50"}} for i in ids]}}


class CompleteCategoryTests(unittest.TestCase):
    def scrape(self, first, rest, seen=None):
        client = MagicMock(first=first)
        client.fetch.side_effect = rest
        with patch.object(plus, "PlusListingClient", return_value=client):
            result = plus.scrape_complete_plus_category(MagicMock(), URL, category="Other", seen=seen)
        return result, client

    def test_every_page_and_cross_category_duplicates(self):
        seen = {"https://www.plus.nl/producten/1"}
        rows, client = self.scrape(payload([1, 2]), [payload([3])], seen)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(seen), 3)
        client.fetch.assert_called_once_with(2)

    def test_fully_overlapping_category_is_complete_not_empty_failure(self):
        rows, _ = self.scrape(payload([1], 1, 1), [], {"https://www.plus.nl/producten/1"})
        self.assertEqual(rows, [])

    def test_partial_pages_never_mutate_global_seen(self):
        for failed in (payload([]), payload([1, 2]), payload([3], total=4),
                       {"TotalPages": 2}, payload([3], pages=1)):
            with self.subTest(failed=failed):
                seen = {"existing"}
                with self.assertRaises(ValueError):
                    self.scrape(payload([1, 2]), [failed], seen)
                self.assertEqual(seen, {"existing"})

    def test_crashed_request_does_not_pollute_retry(self):
        seen = set()
        with self.assertRaises(RuntimeError):
            self.scrape(payload([1, 2]), [RuntimeError("Target crashed")], seen)
        self.assertEqual(seen, set())
        rows, _ = self.scrape(payload([1, 2]), [payload([3])], seen)
        self.assertEqual(len(rows), 3)

    def test_insufficient_unique_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.scrape(payload([1]), [payload([2])])

    def test_malformed_rows_rejected(self):
        bad = payload([1], 1, 1)
        bad["ProductList"]["List"] = [{"PLP_Str": {}}]
        with self.assertRaisesRegex(ValueError, "malformed"):
            self.scrape(bad, [])

    def test_page_limit_and_missing_totals_fail_closed(self):
        for data in ({}, payload([1], 251, 1), payload([], 0, 0)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.scrape(data, [])


class ListingRequestTests(unittest.TestCase):
    def test_bootstrap_matches_category_page_and_origin_and_releases_document(self):
        page = MagicMock()
        response = MagicMock(status=200)
        response.url = "https://www.plus.nl/screenservices/" + plus.PLP_API_FRAGMENT
        response.request.url = response.url
        response.request.post_data_json = {"screenData": {"variables": {
            "CategorySlug": "baby-drogisterij", "PageNumber": 1}}}
        response.request.all_headers.return_value = {
            "content-type": "application/json", "x-csrftoken": "test-only",
            "cookie": "do-not-copy", "authorization": "do-not-copy"}
        response.json.return_value = {"data": payload([1, 2])}
        page.expect_response.return_value.__enter__.return_value.value = response
        client = plus.PlusListingClient(page, URL)
        predicate = page.expect_response.call_args.args[0]
        self.assertTrue(predicate(response))
        response.request.post_data_json["screenData"]["variables"]["PageNumber"] = 2
        self.assertFalse(predicate(response))
        response.request.post_data_json["screenData"]["variables"].update(PageNumber=1, CategorySlug="wrong")
        self.assertFalse(predicate(response))
        response.url = "https://evil.test/" + plus.PLP_API_FRAGMENT
        self.assertFalse(predicate(response))
        self.assertEqual(client.headers, {"content-type": "application/json", "x-csrftoken": "test-only"})
        page.goto.assert_any_call("about:blank", wait_until="commit")

    def client(self):
        client = object.__new__(plus.PlusListingClient)
        client.body = {"screenData": {"variables": {"PageNumber": 1, "URLPageNumber": 1}}}
        client.headers = {"content-type": "application/json"}
        client.url = "https://www.plus.nl/screenservices/" + plus.PLP_API_FRAGMENT
        client.context = MagicMock()
        return client

    def test_page_request_disposed_and_template_not_mutated(self):
        client = self.client()
        response = client.context.post.return_value
        response.status = 200
        response.json.return_value = {"data": payload([3])}
        self.assertEqual(client.fetch(2), payload([3]))
        args = client.context.post.call_args.kwargs
        self.assertEqual(args["data"]["screenData"]["variables"]["PageNumber"], 2)
        self.assertEqual(args["data"]["screenData"]["variables"]["URLPageNumber"], 2)
        self.assertEqual(client.body["screenData"]["variables"]["PageNumber"], 1)
        self.assertEqual(args["max_redirects"], 0)
        response.dispose.assert_called_once()

    def test_transient_retries_are_bounded_and_disposed(self):
        client = self.client()
        response = client.context.post.return_value
        response.status = 503
        with patch.object(plus.time, "sleep"), self.assertRaises(plus.PlaywrightTimeoutError):
            client.fetch(2)
        self.assertEqual(response.dispose.call_count, 3)
        self.assertEqual(client.context.post.call_count, 3)

    def test_auth_failures_and_redirects_are_not_retried(self):
        for status in (302, 401, 403):
            client = self.client()
            response = client.context.post.return_value
            response.status = status
            with self.assertRaises(ValueError):
                client.fetch(2)
            response.dispose.assert_called_once()
            client.context.post.assert_called_once()

    def test_invalid_json_disposed(self):
        client = self.client()
        response = client.context.post.return_value
        response.status = 200
        response.json.side_effect = ValueError("invalid")
        with self.assertRaises(ValueError):
            client.fetch(2)
        response.dispose.assert_called_once()

    def test_untrusted_origin_rejected_without_navigation(self):
        page = MagicMock()
        for url in ("http://www.plus.nl/producten/x", "https://evil.test/producten/x",
                    "https://www.plus.nl@evil.test/producten/x", "https://www.plus.nl:444/producten/x"):
            with self.assertRaises(ValueError):
                plus.PlusListingClient(page, url)
        page.goto.assert_not_called()


class CategoryRecoveryTests(unittest.TestCase):
    def test_incomplete_category_fails_main_before_enrichment(self):
        spec = importlib.util.spec_from_file_location("plus_main_test", Path(__file__).resolve().parents[1] / "countries/nl/plus/main.py")
        main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main)
        with (patch.object(main, "sync_playwright"),
              patch.object(main, "scrape_plus_category_isolated", side_effect=RuntimeError("Target crashed")),
              patch.object(main, "write_json_atomic") as write,
              patch.object(main, "enrich_plus_entries_with_pdp_barcodes") as enrich,
              self.assertRaises(SystemExit) as exit_status):
            main.scrape_plus_products([URL])
        self.assertEqual(exit_status.exception.code, 1)
        self.assertEqual(write.call_args.args[1][0]["state"], "failed")
        enrich.assert_not_called()

    def test_live_verifier_rejects_preservation_and_missing_categories(self):
        complete = [{"url": URL, "state": "complete"}]
        self.assertEqual(refresh_failures({"outcome": "refreshed"}, complete, [URL]), [])
        self.assertTrue(refresh_failures({"outcome": "preserved"}, complete, [URL]))
        self.assertTrue(refresh_failures({"outcome": "refreshed"}, [], [URL]))
        self.assertTrue(refresh_failures({"outcome": "refreshed"}, [{"url": URL, "state": "failed"}], [URL]))

    def test_crash_relaunches_browser_and_preserves_seen(self):
        browsers = [MagicMock(), MagicMock()]
        seen = set()
        with (patch.object(plus, "launch_browser", side_effect=browsers) as launch,
              patch.object(plus, "scrape_complete_plus_category", side_effect=[RuntimeError("Target crashed"), [{"name": "ok"}]])):
            result = plus.scrape_plus_category_isolated(MagicMock(), URL, category="Other", seen=seen)
        self.assertEqual(result, [{"name": "ok"}])
        self.assertEqual(launch.call_count, 2)
        for browser in browsers:
            browser.close.assert_called_once()

    def test_exhaustion_fails_even_if_browser_cleanup_also_fails(self):
        browser = MagicMock()
        browser.close.side_effect = RuntimeError("closed")
        with (patch.object(plus, "launch_browser", return_value=browser),
              patch.object(plus, "scrape_complete_plus_category", side_effect=ValueError("incomplete")),
              self.assertRaisesRegex(ValueError, "incomplete")):
            plus.scrape_plus_category_isolated(MagicMock(), URL, category="Other", seen=set())
        self.assertEqual(browser.close.call_count, 2)
