import unittest
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from dirk_price import card_price, corroborate_card


class DirkPriceTests(unittest.TestCase):
    def test_cents_are_decoded_before_sanitizer_adds_decimal_places(self):
        for parts, price in [(["95"], "0.95"), (["59"], "0.59"), (["5"], "0.05"), (["1", "99"], "1.99"), (["10", "00"], "10.00")]:
            self.assertEqual(card_price(parts), price)
        for parts in [[], ["100"], ["1", "9"], ["1", "00", "99"]]:
            self.assertEqual(card_price(parts), "")

    def test_jsonld_only_corroborates_the_same_product_and_price(self):
        entry = {"raw_text": "95\n\nMelkunie Halfvolle melk\n\n500 ml", "link": "https://www.dirk.nl/product/6247"}
        metadata = [{"url": entry["link"], "price": "0.95", "barcode": "8712345678906"}]
        result = corroborate_card(dict(entry), metadata)
        self.assertEqual(result["barcode"], "8712345678906")
        self.assertEqual(result["sourceMethod"], "dom_cards_json_ld")
        for change in [{"price": "95.00"}, {"url": "https://www.dirk.nl/product/other"}]:
            self.assertNotIn("barcode", corroborate_card(dict(entry), [{**metadata[0], **change}]))

    def test_real_postprocess_steps_preserve_sub_euro_prices(self):
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / "config/stores.json").read_text())
        steps = config["countries"]["nl"]["stores"]["dirk"]["pipeline"][1:]
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            (target / "config").mkdir()
            shutil.copy(root / "config/stores.json", target / "config/stores.json")
            (target / "JSONs").mkdir()
            rows = [{"raw_text": raw, "image": "", "category": "Dairy & Eggs"} for raw in [
                "95\n\nMelkunie Halfvolle melk\n\n500 ml",
                "1\n19\n\nMelkunie Volle melk\n\n500 ml",
                "ACTIE\n55\n\nMelkan Halfvolle melk\n\n500 ml",
            ]]
            (target / "JSONs/dirk.json").write_text(json.dumps(rows))
            for step in steps:
                shutil.copy(root / "countries/nl/dirk" / step, target / step)
                subprocess.run([sys.executable, step], cwd=target, env={**os.environ, "PYTHONPATH": str(root)}, check=True, capture_output=True)
            prices = sorted(float(row["p"]) for row in json.loads((target / "dirk_all.json").read_text()))
            self.assertEqual(prices, [0.55, 0.95, 1.19])
