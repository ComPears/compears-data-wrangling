import io
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

import ah_api_client as ah


class AhReliabilityTests(unittest.TestCase):
    def test_access_denied_is_not_retried_or_body_logged(self):
        error = HTTPError("https://api.ah.nl/test", 403, "Forbidden", {}, io.BytesIO(b"sensitive response"))
        with patch.object(ah.urllib.request, "urlopen", side_effect=error) as request:
            with self.assertRaisesRegex(ah.AhApiError, "access_denied") as caught:
                ah._request("GET", "/test")
        self.assertEqual(request.call_count, 1)
        self.assertNotIn("sensitive response", str(caught.exception))

    def test_503_retries_are_bounded_and_classified(self):
        errors = [HTTPError("https://api.ah.nl/test", 503, "Unavailable", {}, io.BytesIO(b"edge")) for _ in range(3)]
        with (patch.object(ah.urllib.request, "urlopen", side_effect=errors) as request,
              patch.object(ah.time, "sleep")):
            with self.assertRaisesRegex(ah.AhApiError, "upstream_unavailable"):
                ah._request("POST", "/test")
        self.assertEqual(request.call_count, 3)

    def test_pagination_limit_cannot_silently_truncate(self):
        with patch.object(ah, "_request", return_value={"products": [{"id": 1}],
                                                       "page": {"totalPages": 56}}):
            with self.assertRaises(ah.AhPaginationLimitError):
                ah._fetch_paginated("token", "1")

    def test_limit_splits_into_child_taxonomies(self):
        with (patch.object(ah, "_fetch_paginated", side_effect=[
                  ah.AhPaginationLimitError("too many pages"), [{"id": 1}], [{"id": 1}, {"id": 2}]]),
              patch.object(ah, "_request", return_value={"filters": [
                  {"id": "taxonomy", "options": [{"id": 2}, {"id": 3}]}]}),
              patch.object(ah.time, "sleep")):
            self.assertEqual(ah.fetch_taxonomy_products("token", "1"), [{"id": 1}, {"id": 2}])

    def test_empty_intermediate_page_is_failure(self):
        with (patch.object(ah, "_request", side_effect=[
                  {"products": [{"id": 1}], "page": {"totalPages": 3}},
                  {"products": [], "page": {"totalPages": 3}}]),
              patch.object(ah.time, "sleep")):
            with self.assertRaisesRegex(ah.AhApiError, "empty page 1"):
                ah._fetch_paginated("token", "1")
