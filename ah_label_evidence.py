"""Explicit AH trade-item facts from detail requests already made for GTINs."""
from __future__ import annotations

import math
from typing import Any

from label_evidence import extract_label_evidence


def label_from_ah_detail(detail: dict[str, Any], webshop_id: str) -> dict | None:
    # Bind the detail to the requested listing, never its category/related items.
    if not str(webshop_id).isdigit() or str(detail.get("productId")) != str(webshop_id):
        return None
    trade = detail.get("tradeItem")
    if not isinstance(trade, dict):
        return None
    node: dict[str, Any] = {"ingredients": trade.get("foodAndBeverageIngredientStatement")}
    # Only explicit affirmative retailer properties; exclude_* is NOT a claim.
    properties = detail.get("properties") or {}
    diets = {"sp_include_dieet_veganistisch": "VeganDiet", "sp_include_dieet_vegetarisch": "VegetarianDiet"}
    if isinstance(properties, dict):
        node["suitableForDiet"] = [diet for key, diet in diets.items() if properties.get(key)]
        if properties.get("da_sugar_added_or_no_sugar_added") == ["Geen toegevoegde suikers"]:
            node["additionalProperty"] = [{"name": "no added sugar", "value": True}]
    headers = (trade.get("nutritionalInformation") or {}).get("nutrientHeaders") or []
    candidates = []
    for header in headers[:10] if isinstance(headers, list) else []:
        if not isinstance(header, dict) or (header.get("preparationStateCode") or {}).get("value") != "UNPREPARED":
            continue
        basis = header.get("nutrientBasisQuantity") or {}
        unit = (basis.get("measurementUnitCode") or {}).get("value")
        if basis.get("value") != 100 or unit not in {"g", "ml"}:
            continue
        facts: dict[str, Any] = {"servingSize": f"100 {unit}"}
        keys = {"PRO-": "proteinContent", "SUGAR-": "sugarContent", "FIBTG": "fiberContent", "FAT": "fatContent"}
        for fact in header.get("nutrientDetail") or []:
            if not isinstance(fact, dict):
                continue
            key = keys.get((fact.get("nutrientTypeCode") or {}).get("value"))
            precision = (fact.get("measurementPrecisionCode") or {}).get("value")
            quantities = fact.get("quantityContained") or []
            if not key or precision not in {None, "APPROXIMATELY", "EXACT"} or len(quantities) != 1:
                continue
            quantity = quantities[0]
            value = quantity.get("value")
            if (quantity.get("measurementUnitCode") or {}).get("value") == "g" and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1000:
                facts[key] = f"{value} g"
        if len(facts) > 1:
            candidates.append(facts)
    # Ambiguous prepared/portion panels are never merged or converted.
    if candidates and all(value == candidates[0] for value in candidates):
        node["nutrition"] = candidates[0]
    return extract_label_evidence(node, source_url=f"https://www.ah.nl/producten/product/wi{webshop_id}", method="retailer_api")
