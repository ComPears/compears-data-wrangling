import unittest
from ah_label_evidence import label_from_ah_detail


class AhLabelsTest(unittest.TestCase):
    def detail(self):
        return {"productId": "123", "properties": {"sp_exclude_dieet_veganistisch": ["Veganistisch"], "da_sugar_added_or_no_sugar_added": ["Geen toegevoegde suikers"]}, "tradeItem": {
            "foodAndBeverageIngredientStatement": "Ingrediënten: melk.",
            "nutritionalInformation": {"nutrientHeaders": [{"preparationStateCode": {"value": "UNPREPARED"}, "nutrientBasisQuantity": {"value": 100, "measurementUnitCode": {"value": "ml"}},
                "nutrientBasisQuantityDescription": ["200 milliliter"], "nutrientDetail": [{"nutrientTypeCode": {"value": "PRO-"}, "quantityContained": [{"value": 3.7, "measurementUnitCode": {"value": "g"}}]}, {"nutrientTypeCode": {"value": "FIBTG"}, "quantityContained": [{"value": 0, "measurementUnitCode": {"value": "g"}}]}]}]}}}

    def test_explicit_basis_beats_unrelated_portion_description(self):
        result = label_from_ah_detail(self.detail(), "123")
        self.assertEqual(result["nutrients"], {"basis": "100ml", "servingSize": "100 ml", "proteinG": 3.7, "fiberG": 0})
        self.assertEqual(result["claims"], ["no-added-sugar"])
        self.assertEqual(result["method"], "retailer_api")
        self.assertEqual(result["sourceUrl"], "https://www.ah.nl/producten/product/wi123")

    def test_wrong_listing_and_prepared_or_less_than_values(self):
        self.assertIsNone(label_from_ah_detail(self.detail(), "124"))
        detail = self.detail()
        header = detail["tradeItem"]["nutritionalInformation"]["nutrientHeaders"][0]
        header["preparationStateCode"]["value"] = "PREPARED"
        self.assertNotIn("nutrients", label_from_ah_detail(detail, "123"))
        header["preparationStateCode"]["value"] = "UNPREPARED"
        for fact in header["nutrientDetail"]:
            fact["measurementPrecisionCode"] = {"value": "LESS_THAN"}
        self.assertNotIn("nutrients", label_from_ah_detail(detail, "123"))
