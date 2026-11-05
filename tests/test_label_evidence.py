import json
import unittest
from label_evidence import extract_label_evidence
from scripts.refresh_label_evidence import evidence_from_html, trusted_url


class LabelEvidenceTests(unittest.TestCase):
    def test_extracts_explicit_facts_and_keeps_zero_sugar(self):
        node = {"ingredients": "Oats, water", "suitableForDiet": "https://schema.org/VeganDiet", "nutrition": {"servingSize": "100 ml", "sugarContent": "0 g", "proteinContent": "3.2 g"}}
        value = extract_label_evidence(node, source_url="https://shop.example/p/milk")
        self.assertEqual(value["nutrients"]["sugarG"], 0)
        self.assertEqual(value["nutrients"]["basis"], "100ml")
        self.assertEqual(value["claims"], ["vegan"])
        self.assertNotIn("no-added-sugar", value["claims"])

    def test_never_infers_from_name_or_missing_serving_basis(self):
        self.assertIsNone(extract_label_evidence({"name": "Vegan sugar-free milk", "nutrition": {"proteinContent": "5 g"}}, source_url="https://shop.example/p/milk"))
        value = extract_label_evidence({"nutrition": {"servingSize": "30 g", "proteinContent": "10 g"}}, source_url="https://shop.example/p/milk")
        self.assertEqual(value["nutrients"]["basis"], "serving")
        self.assertEqual(value["nutrients"]["servingSize"], "30 g")

    def test_product_binding_excludes_recipes_related_items_and_wrong_variants(self):
        url = "https://shop.example/p/milk"
        nodes = [{"@type": "Recipe", "url": url, "ingredients": "Not product ingredients"}, {"@type": "Product", "url": url + "-other", "ingredients": "Other"}, {"@type": "Product", "url": url, "ingredients": "Oats, water"}]
        html = '<script type="application/ld+json">' + json.dumps(nodes) + '</script>'
        self.assertEqual(evidence_from_html(html, url)["ingredients"], "Oats, water")
        self.assertIsNone(evidence_from_html(html, url + "-missing"))

    def test_trusted_retailer_boundary_rejects_credentials_other_hosts_and_schemes(self):
        origin = "https://www.dirk.nl"
        self.assertEqual(trusted_url(origin + "/product/milk", origin), origin + "/product/milk")
        for url in ["http://www.dirk.nl/p", "https://www.dirk.nl.evil.example/p", "https://user:secret@www.dirk.nl/p", "https://127.0.0.1/p", "file:///etc/passwd", origin + "/"]:
            self.assertIsNone(trusted_url(url, origin))

    def test_jsonld_evidence_survives_both_country_structure_steps(self):
        from countries.uk._shared.uk_product import structure_raw_products as uk
        from countries.de._shared.de_product import structure_raw_products as de
        evidence = extract_label_evidence({"ingredients": "Water, oats"}, source_url="https://shop.example/p/milk")
        for transform in (uk, de):
            rows = transform([{"n": "Oat Milk", "p": "1.25", "s": "1 l", "i": "https://shop.example/p/milk", "labelEvidence": evidence}])
            self.assertEqual(rows[0]["labelEvidence"], evidence)
