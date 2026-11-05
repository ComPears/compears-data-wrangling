"""Source-backed label facts; never infer ingredient safety from product names."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

CLAIMS = {
    "VeganDiet": "vegan", "VegetarianDiet": "vegetarian", "GlutenFreeDiet": "gluten-free",
    "LowLactoseDiet": "low-lactose", "HalalDiet": "halal", "KosherDiet": "kosher",
}


def _plain(value: Any, limit: int = 4000) -> str | None:
    if not isinstance(value, str) or len(value) > limit or re.search(r"[<>\x00]", value):
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def extract_label_evidence(node: dict, *, source_url: str, method: str = "json_ld", observed_at: str | None = None) -> dict | None:
    """Consume explicit facts belonging to this Product, not nearby Recipe nodes."""
    ingredients = _plain(node.get("ingredients") or node.get("ingredientStatement"))
    properties = node.get("additionalProperty") or []
    if not isinstance(properties, list):
        properties = [properties]
    claims = []
    diets = node.get("suitableForDiet") or []
    if not isinstance(diets, list):
        diets = [diets]
    for diet in diets:
        claim = CLAIMS.get(str(diet).rsplit("/", 1)[-1])
        if claim:
            claims.append(claim)
    for prop in properties[:100]:
        if not isinstance(prop, dict):
            continue
        name = str(prop.get("name") or "").strip().casefold()
        if name in {"ingredients", "ingredient statement", "ingrediënten", "zutaten"}:
            ingredients = ingredients or _plain(prop.get("value"))
        if name in {"no added sugar", "zonder toegevoegde suiker", "ohne zuckerzusatz"} and prop.get("value") in [True, "true", "yes"]:
            claims.append("no-added-sugar")
    nutrition = node.get("nutrition")
    nutrients = None
    if isinstance(nutrition, dict):
        serving = _plain(nutrition.get("servingSize"), 80)
        if serving:
            compact = serving.lower().replace(" ", "")
            basis = "100g" if compact == "100g" else "100ml" if compact == "100ml" else "serving"
            facts = {}
            for source, target in [("proteinContent", "proteinG"), ("sugarContent", "sugarG"), ("fiberContent", "fiberG"), ("fatContent", "fatG")]:
                value = nutrition.get(source)
                match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(g|grams?|gramm)\s*", value, re.I) if isinstance(value, str) else None
                if match and 0 <= float(match[1].replace(",", ".")) <= 1000:
                    facts[target] = float(match[1].replace(",", "."))
            if facts:
                nutrients = {"basis": basis, "servingSize": serving, **facts}
    if not ingredients and not claims and not nutrients:
        return None
    evidence = {"version": 1, "sourceUrl": source_url, "method": method,
                "observedAt": observed_at or datetime.now(timezone.utc).isoformat(), "claims": sorted(set(claims))}
    if ingredients:
        evidence["ingredients"] = ingredients
    if nutrients:
        evidence["nutrients"] = nutrients
    return evidence
