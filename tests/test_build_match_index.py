from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data_contract import parse_quantity
from scripts import build_match_index


class BuildMatchIndexTests(unittest.TestCase):
    def test_only_confidence_checked_cross_store_groups_are_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "one.json"
            second = root / "two.json"
            quantity = parse_quantity("500 g")
            first.write_text(
                json.dumps(
                    [
                        {
                            "ik": "tok:barilla|spaghetti|500g",
                            "bn": "barilla",
                            "brandSource": "retailer",
                            "cn": "barilla spaghetti",
                            "quantity": quantity,
                            "n": "Barilla Spaghetti 500 g",
                            "p": "1.50",
                        },
                        {
                            "ik": "tok:unknown|milk|1000ml",
                            "cn": "milk",
                            "quantity": parse_quantity("1 l"),
                            "n": "Whole Milk 1 l",
                            "p": "1.00",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            second.write_text(
                json.dumps(
                    [
                        {
                            "ik": "tok:barilla|spaghetti|500g",
                            "bn": "barilla",
                            "brandSource": "retailer",
                            "cn": "barilla spaghetti",
                            "quantity": quantity,
                            "n": "Barilla Spaghetti 500g",
                            "p": "1.60",
                        },
                        {
                            "ik": "tok:unknown|milk|1000ml",
                            "cn": "milk",
                            "quantity": parse_quantity("1 l"),
                            "n": "Whole Milk 1 l",
                            "p": "1.10",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(
                build_match_index,
                "all_catalog_paths",
                return_value=[("uk", "one", first), ("uk", "two", second)],
            ):
                report, quality = build_match_index.build_country("uk")

        self.assertEqual(len(report["groups"]), 1)
        self.assertEqual(report["groups"][0]["matchKey"], "tok:barilla|spaghetti|500g")
        self.assertEqual(report["groups"][0]["confidence"], 0.98)
        self.assertEqual(quality["matchedOffers"], 2)
        self.assertEqual(quality["rejectedGroups"], 1)

    def test_gtin_key_must_match_every_offer_barcode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "one.json"
            second = root / "two.json"
            key = "ean:4006381333931"
            first.write_text(json.dumps([{"ik": key, "b": "4006381333931"}]), encoding="utf-8")
            second.write_text(json.dumps([{"ik": key, "b": "8718452709458"}]), encoding="utf-8")
            with patch.object(
                build_match_index,
                "all_catalog_paths",
                return_value=[("nl", "one", first), ("nl", "two", second)],
            ):
                report, quality = build_match_index.build_country("nl")

        self.assertEqual(report["groups"], [])
        self.assertEqual(quality["rejectedGroups"], 1)


if __name__ == "__main__":
    unittest.main()
