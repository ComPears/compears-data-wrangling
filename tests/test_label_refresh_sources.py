import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import refresh_label_evidence as labels


class LabelRefreshSourcesTest(unittest.TestCase):
    def fixture(self, root):
        (root / 'config').mkdir()
        (root / 'config/stores.json').write_text((labels.ROOT / 'config/stores.json').read_text())
        catalog = root / 'countries/nl/albert-heijn/structured_all_merged.json'
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps([{'n': 'Milk', 'p': '1.25', 'productUrl': f'https://www.ah.nl/producten/product/wi{id}'} for id in ['123', '124']]))
        return catalog

    def test_public_api_facts_share_the_page_sample_budget_and_never_change_prices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.fixture(root); before = catalog.read_bytes()
            def detail(_token, product_id, **_kwargs):
                return {'productId': product_id, 'tradeItem': {'foodAndBeverageIngredientStatement': 'Ingrediënten: melk.'}}
            with (patch.object(labels, 'get_anonymous_token', return_value='fixture-only') as auth,
                  patch.object(labels, 'fetch_product_detail', side_effect=detail) as fetch,
                  patch.object(labels, 'fetch_evidence') as html,
                  patch.object(labels.time, 'sleep')):
                result = labels.refresh(root, per_store=2)
            self.assertEqual(result['found'], 2)
            self.assertEqual(result['countries'], {'nl': 2, 'uk': 0, 'de': 0})
            self.assertEqual(result['outcomes']['retailer-api-facts'], 2)
            auth.assert_called_once_with(timeout=8, attempts=1)
            self.assertEqual(fetch.call_count, 2)
            for call in fetch.call_args_list:
                self.assertEqual(call.kwargs, {'timeout': 8, 'attempts': 1, 'max_response_bytes': 1_000_000})
            html.assert_not_called()
            self.assertEqual(catalog.read_bytes(), before)
            self.assertEqual({e['method'] for e in json.loads((root / 'label-evidence/nl.json').read_text())}, {'retailer_api'})

    def test_unavailable_api_is_not_retried_or_reported_as_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root)
            with (patch.object(labels, 'get_anonymous_token', side_effect=RuntimeError('unavailable')) as auth,
                  patch.object(labels, 'fetch_evidence', return_value=None),
                  patch.object(labels.time, 'sleep')):
                result = labels.refresh(root, per_store=2)
            auth.assert_called_once()
            self.assertEqual(result['found'], 0)
            self.assertEqual(result['outcomes']['retailer-api-unavailable'], 1)

    def test_arbitrary_origins_are_rejected_before_any_request(self):
        with patch.object(labels.urllib.request, 'build_opener') as request:
            self.assertIsNone(labels.fetch_evidence('https://untrusted.example/p', 'https://untrusted.example'))
        request.assert_not_called()
