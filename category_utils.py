"""Shared product category normalization for all supermarket pipelines."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# Must match compear/src/services/categoryService.ts ProductCategory values.
CANONICAL_CATEGORIES = frozenset(
    {
        "Fruits & Vegetables",
        "Dairy & Eggs",
        "Meat & Seafood",
        "Beverages",
        "Bakery",
        "Snacks",
        "Frozen Foods",
        "Pantry",
        "Personal Care",
        "Household",
        "Other",
    }
)

DEFAULT_CATEGORY = "Other"

AH_CATEGORY_MAP: dict[str, str] = {
    "groente_aardappelen": "Fruits & Vegetables",
    "fruit_verse_sappen": "Fruits & Vegetables",
    "maaltijden_salades": "Pantry",
    "vegetarisch_vegan_en_plantaardig": "Pantry",
    "vlees": "Meat & Seafood",
    "vleeswaren": "Meat & Seafood",
    "bakkerij": "Bakery",
    "zuivel": "Dairy & Eggs",
    "glutenvrij": "Pantry",
    "borrel_chips_snacks": "Snacks",
    "pasta_rijst_wereldkeuken": "Pantry",
    "soepen_sauzen_kruiden_olie": "Pantry",
    "koek_snoep_chocolade": "Snacks",
    "ontbijtgranen_beleg": "Pantry",
    "tussendoortjes": "Snacks",
    "diepvries": "Frozen Foods",
    "koffie_thee": "Beverages",
    "frisdrank_sappen_water": "Beverages",
    "bier_wijn_aperitieven": "Beverages",
    "drogisterij": "Personal Care",
    "gezondheid_en_sport": "Personal Care",
    "huishouden": "Household",
    "baby_en_kind": "Personal Care",
    "huisdier": "Other",
    "koken_tafelen_vrije_tijd": "Household",
    "ah_voordeelshop": "Other",
}

# (path keywords, category) — first match wins; order matters.
PATH_CATEGORY_RULES: list[tuple[tuple[str, ...], str]] = [
    (("drogisterij", "baby", "verzorging", "zonnebrand", "douche", "shampoo"), "Personal Care"),
    (("huishoud", "wasmiddel", "schoonmaak", "toiletpapier"), "Household"),
    (("diepvries", "frozen", "ijs"), "Frozen Foods"),
    (("zuivel", "melk", "kaas", "eieren", "boter", "yoghurt", "kwark"), "Dairy & Eggs"),
    (("vlees", "vis", "kip", "gehakt", "rundvlees", "varkensvlees", "zalm", "tonijn"), "Meat & Seafood"),
    (("fruit", "groente", "aardappel", "salade", "sla", "tomaten"), "Fruits & Vegetables"),
    (("brood", "bakkerij", "gebak", "bolletje", "croissant", "beschuit"), "Bakery"),
    (("chips", "koek", "snoep", "chocolade", "chocola", "snack"), "Snacks"),
    (("bier", "wijn", "frisdrank", "sap", "koffie", "thee", "drank"), "Beverages"),
    (("pasta", "rijst", "conserven", "soep", "saus", "wereldkeuken", "ontbijt", "beleg"), "Pantry"),
]


def _normalize_slug(value: str) -> str:
    return value.lower().replace("_", "-").replace(",", "-")


def _match_path_category(text: str) -> str | None:
    slug = _normalize_slug(text)
    for keywords, category in PATH_CATEGORY_RULES:
        if any(keyword in slug for keyword in keywords):
            return category
    return None


def ensure_canonical(category: str | None) -> str:
    if category and category in CANONICAL_CATEGORIES:
        return category
    return DEFAULT_CATEGORY


def category_from_ah_key(key: str) -> str:
    return ensure_canonical(AH_CATEGORY_MAP.get(key) or _match_path_category(key))


def category_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return DEFAULT_CATEGORY
    return ensure_canonical(_match_path_category(path))


def category_from_coop_url(url: str) -> str:
    # e.g. boodschappen.fruit.appels or boodschappen.zuivel.melk
    slug = url.split("/categorie/")[-1].split("?")[0]
    return ensure_canonical(_match_path_category(slug.replace(".", "-")))


def infer_category_from_name(name: str) -> str:
    """Fallback when scrape metadata is missing (e.g. LIDL single-page scrape)."""
    lower = name.lower()
    if re.search(r"\bspf\d*", lower) or "zonnebrand" in lower or "sun protection" in lower:
        return "Personal Care"
    if any(k in lower for k in ("wasmiddel", "afwasmiddel", "toiletpapier", "keukenrol")):
        return "Household"
    if any(k in lower for k in ("shampoo", "tandpasta", "deodorant", "douchegel")):
        return "Personal Care"
    matched = _match_path_category(lower.replace(" ", "-"))
    return ensure_canonical(matched)


def structured_with_category(entry: dict[str, Any], structured: dict[str, Any]) -> dict[str, Any]:
    """Attach canonical category field `c` to a structured product record."""
    category = entry.get("category")
    if not category:
        category = infer_category_from_name(entry.get("raw_text", entry.get("n", "")))
    structured["c"] = ensure_canonical(category)
    return structured
