import importlib.util
import json
import tempfile
import sys
from unittest.mock import Mock
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aldi_restructure", ROOT / "countries/nl/aldi/restructure.py")
aldi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aldi)
clean_spec = importlib.util.spec_from_file_location("aldi_clean", ROOT / "countries/nl/aldi/clean_aldi.py")
clean = importlib.util.module_from_spec(clean_spec)
clean_spec.loader.exec_module(clean)
sys.path.insert(0, str(ROOT / "countries/nl/aldi"))
main_spec = importlib.util.spec_from_file_location("aldi_main", ROOT / "countries/nl/aldi/main.py")
main = importlib.util.module_from_spec(main_spec)
main_spec.loader.exec_module(main)


class AldiNlTests(unittest.TestCase):
    def test_price_readiness_checks_newly_loaded_page_not_previous_prices(self):
        page = Mock()
        page.locator.return_value.evaluate_all.return_value = []
        main.extract_priced_cards(page, start_index=24)
        args, kwargs = page.wait_for_function.call_args
        self.assertIn('.slice(start)', args[0])
        self.assertEqual(kwargs['arg'], 24)

    def test_deduplication_preserves_same_name_pack_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            small = {"n": "Whole Milk", "s": "1 l"}
            large = {"n": "Whole Milk", "s": "2 l"}
            path.write_text(json.dumps([small, large, small]))
            self.assertEqual(clean.remove_duplicate_items_from_json(path), [small, large])

    def test_explicit_current_price_and_sales_unit_override_ambiguous_text(self):
        row = aldi.transform_entry({
            "raw_text": "DAYLICIOUS\nAardappelpartjes gekruid\n1.99\n1.29\n450 g\nkg = 2.87",
            "name": "Aardappelpartjes gekruid", "price": "1.29", "size": "450 g",
            "brand": "DAYLICIOUS", "productUrl": "https://www.aldi.nl/product/aardappelpartjes-1226110.html",
            "image": "https://example.com/product.jpg",
        })
        self.assertEqual(row["p"], "1.29")
        self.assertEqual(row["s"], "450 g")
        self.assertEqual(row["n"].casefold(), "aardappelpartjes gekruid")
        self.assertEqual(row["brandSource"], "retailer")
        self.assertIn("/product/", row["productUrl"])

    def test_missing_explicit_price_does_not_fall_back_to_unit_or_old_price(self):
        row = aldi.transform_entry({"raw_text": "Whole Milk\n1.99\n1 l", "name": "Whole Milk",
                                    "price": "", "size": "1 l"})
        self.assertEqual(row["p"], "")

    def test_legacy_raw_text_is_still_supported(self):
        row = aldi.transform_entry({"raw_text": "Whole Milk\n1.99\n1 l"})
        self.assertEqual(row["p"], "1.99")
