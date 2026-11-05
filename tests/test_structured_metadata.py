import unittest
from datetime import datetime, timezone
from structured_metadata import extract_products, extract_page_products, enrich_rows


class StructuredMetadataTests(unittest.TestCase):
    def product(self, offers=None, **extra):
        return {"@type": "Product", "name": "Milk", "url": "/products/milk", "size": {"value": 1, "unitCode": "LTR"},
                "offers": offers or {"@type": "Offer", "price": "1.25", "priceCurrency": "GBP"}, **extra}

    def extract(self, payload):
        return extract_products(payload, base_url="https://shop.example", currency="GBP", now=datetime(2026, 11, 5, tzinfo=timezone.utc))

    def test_nested_itemlist_and_cross_script_offer_reference(self):
        product = self.product({"@id": "#offer"})
        offer = {"@id": "#offer", "@type": "Offer", "price": "1.25", "priceCurrency": "GBP"}
        result = self.extract([{"@type": "ItemList", "itemListElement": [{"item": product}]}, {"@graph": [offer]}])
        self.assertEqual(result[0]["price"], "1.25")
        self.assertEqual(result[0]["size"], "1 l")
        self.assertEqual(result[0]["availability"], "")

    def test_rejects_unsafe_or_non_public_prices(self):
        for change in [
            {"priceCurrency": "EUR"}, {"price": "NaN"}, {"price": "Infinity"}, {"price": -1},
            {"price": "1.255"}, {"@type": "AggregateOffer"}, {"availability": "https://schema.org/OutOfStock"},
            {"priceValidUntil": "2026-11-04"}, {"validFrom": "2026-11-06"}, {"validForMemberTier": "club"},
            {"url": "https://evil.example/milk"}, {"itemCondition": "https://schema.org/UsedCondition"},
        ]:
            with self.subTest(change=change):
                offer = {"@type": "Offer", "price": "1.25", "priceCurrency": "GBP", **change}
                self.assertEqual(self.extract(self.product(offer)), [])

    def test_does_not_select_cheapest_ambiguous_offer(self):
        offers = [{"price": p, "priceCurrency": "GBP"} for p in ["1.25", "0.99"]]
        self.assertEqual(self.extract(self.product(offers)), [])

    def test_valid_until_includes_whole_day_and_deduplicates(self):
        product = self.product({"price": "1.25", "priceCurrency": "GBP", "priceValidUntil": "2026-11-05"})
        self.assertEqual(len(self.extract([product, product])), 1)

    def test_supports_euro_retailer_and_ignores_non_products(self):
        product = self.product({"price": "1.25", "priceCurrency": "EUR"})
        result = extract_products(product, base_url="https://shop.example", currency="EUR")
        self.assertEqual(len(result), 1)
        self.assertEqual(self.extract({"@type": "Organization", "name": "Shop"}), [])

    def test_enrichment_requires_url_and_price_agreement(self):
        rows = [{"n": "Milk", "p": "1.25", "i": "https://shop.example/milk", "sourceMethod": "api", "observedAt": "original"}]
        metadata = [{"p": "1.25", "i": "https://shop.example/milk", "s": "1 l", "b": "8712345678906"}]
        result = enrich_rows(rows, metadata)
        self.assertEqual(result[0]["b"], "8712345678906")
        self.assertEqual(result[0]["sourceMethod"], "api")
        self.assertEqual(result[0]["observedAt"], "original")
        for change in [{"p": "0.99"}, {"i": "https://shop.example/other"}]:
            row = {"p": "1.25", "i": "https://shop.example/milk"}
            self.assertNotIn("b", enrich_rows([row], [{**metadata[0], **change}])[0])

    def test_page_adapter_supports_uk_and_german_normalizers(self):
        import json
        from countries.uk._shared.uk_product import raw_product as uk_factory
        from countries.de._shared.de_product import raw_product as de_factory
        class Page:
            def __init__(self, payload): self.payload = payload
            def locator(self, _selector): return self
            def count(self): return 1
            def nth(self, _index): return self
            def inner_text(self, **_kwargs): return json.dumps(self.payload)
        for currency, factory in [("GBP", uk_factory), ("EUR", de_factory)]:
            with self.subTest(currency=currency):
                rows = extract_page_products(Page(self.product({"price": "1.25", "priceCurrency": currency})), base_url="https://shop.example", currency=currency, factory=factory)
                self.assertEqual(rows[0]["p"], "1.25")
                self.assertEqual(rows[0]["s"], "1 l")
                self.assertEqual(rows[0]["sourceMethod"], "json_ld")

    def test_malformed_references_and_urls_fail_closed(self):
        for offer in [{"@id": []}, {"price": "1.25", "priceCurrency": "GBP", "url": "https://[broken"}, {"price": "1.25", "priceCurrency": "GBP", "url": "/"}]:
            self.assertEqual(self.extract(self.product(offer)), [])


if __name__ == "__main__":
    unittest.main()
