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

# Multilingual product-name rules for every currently exposed market. Keep
# these conservative: "Other" is preferable to a confidently wrong category.
NAME_CATEGORY_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(frozen|tiefk[uü]hl\w*|diepvries\w*|ice cream|eiscreme|"
            r"fish fingers|fischst[aä]bchen|vissticks)\b",
            re.I,
        ),
        "Frozen Foods",
    ),
    (
        re.compile(
            r"\b(shampoo|toothpaste|tandpasta|zahnpasta|deodorant|deo|"
            r"napp(?:y|ies)|windeln?|diapers?|douchegel|shower gel|duschgel|"
            r"zonnebrand|sonnencreme|sun(?:screen|block))\b",
            re.I,
        ),
        "Personal Care",
    ),
    (
        re.compile(
            r"\b(toilet(?:ten)?papier|toilet roll|kitchen roll|k[uü]chenrolle|"
            r"wasmiddel|waschmittel|laundry detergent|afwasmiddel|sp[uü]lmittel|"
            r"washing up liquid|fabric softener|weichsp[uü]ler|bin bags?|"
            r"m[uü]llbeutel|vuilniszakken|cleaner|reiniger)\b",
            re.I,
        ),
        "Household",
    ),
    (
        re.compile(
            r"\b(chocolate milk|chocolademelk|kakaomilch|haferdrink|mandeldrink|"
            r"liebfraumilch|water|wasser|juice|sap|saft|"
            r"coffee|koffie|kaffee|tea|thee|tee|cola|soda|frisdrank|limonade|"
            r"beer|bier|wine|wijn|wein|wei[ßs]wein|rotwein|ros[eé]wein|schaumwein|sekt|"
            r"champagner|cava|espresso|caff[eé]|eierlik[oö]r|prosecco)\b",
            re.I,
        ),
        "Beverages",
    ),
    (
        re.compile(
            r"\b(chocolate|chocolade|schokol\w*|pralinen?|crisps?|chips|biscuits?|cookies?|"
            r"keks\w*|koek(?:jes)?|sweets?|candy|snoep|bonbons?|snacks?|riegel\w*|"
            r"waffel\w*|smarties|nuss)\b",
            re.I,
        ),
        "Snacks",
    ),
    (
        re.compile(
            r"\b(milk|melk|\w*milch\w*|\w*butter\w*|boter|eggs?|eieren?|"
            r"(?:bio|freiland|bodenhaltungs|h[uü]hner)?eier|"
            r"cheese|kaas|\w*k[aä]se\w*|yogh?urt|\w*joghurt\w*|quark|kwark|cream|"
            r"\w*sahne\w*|room|cheddar|gouda|margarine)\b",
            re.I,
        ),
        "Dairy & Eggs",
    ),
    (
        re.compile(
            r"\b(chicken|kip|h[aä]hnchen\w*|beef|rund\w*|pork|varken|schwein\w*|"
            r"mince|gehakt|hackfleisch|bacon|speck|sausages?|wurst\w*|salmon|zalm|"
            r"lachs\w*|cod|kabeljauw|kabeljau|ham|schinken|tuna|tonijn|thunfisch|"
            r"fish|vis|fisch\w*|prawns?|garnelen|herring|hering|salami|chorizo|jerky)\b",
            re.I,
        ),
        "Meat & Seafood",
    ),
    (
        re.compile(
            r"\b(apples?|appel|apfel|bananas?|banaan|banane|potato(?:es)?|aardappel|"
            r"kartoffeln?|tomato(?:es)?|tomaten?|onions?|ui|uien|zwiebeln?|carrots?|"
            r"worteln?|karotten?|broccoli|cucumber|komkommer|gurke|lettuce|sla|salat|"
            r"avocados?|lemons?|citroen|zitrone|grapes?|druiven|trauben|paprika)\b",
            re.I,
        ),
        "Fruits & Vegetables",
    ),
    (
        re.compile(
            r"\b(bread|brood|brot|toast|br[oö]tchen|bread rolls?|croissants?|"
            r"cake|cakes|gebak|kuchen|beschuit)\b",
            re.I,
        ),
        "Bakery",
    ),
    (
        re.compile(
            r"\b(pasta|spaghetti|\w*nudeln?|rice|rijst|reis|flour|meel|mehl|sugar|"
            r"suiker|zucker|salt|zout|salz|pepper|peper|pfeffer|oil|olie|[oö]l|"
            r"vinegar|azijn|essig|ketchup|mayonnaise|mayo|mustard|mosterd|senf|"
            r"jam|marmelade|honey|honing|honig|cereal|m[uü]sli|oats?|haferflocken|"
            r"beans?|bonen|bohnen|tinned tomatoes|dosentomaten|soup|soep|suppe|"
            r"tortellini|sp[aä]tzle|macaroni|crackers?|gherkins?|sauerkraut|"
            r"falafel|syrup|stroop|sirup|spread|aufstrich)\b",
            re.I,
        ),
        "Pantry",
    ),
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
    """Infer a conservative shared category from Dutch, German, or UK names."""
    lower = name.lower()
    if re.search(r"\bspf\s*\d*", lower) or "sun protection" in lower:
        return "Personal Care"
    for pattern, category in NAME_CATEGORY_RULES:
        if pattern.search(lower):
            return category
    matched = _match_path_category(lower.replace(" ", "-"))
    return ensure_canonical(matched)


from barcode_utils import extract_barcode_from_entry
from product_sanitize import sanitize_entry


def structured_with_category(entry: dict[str, Any], structured: dict[str, Any]) -> dict[str, Any]:
    """Attach category, barcode, and sanitized identity fields."""
    category = entry.get("c") or entry.get("category")
    if not category:
        category = infer_category_from_name(entry.get("raw_text", entry.get("n", "")))
    structured["c"] = ensure_canonical(category)

    barcode = extract_barcode_from_entry(entry)
    if barcode:
        structured["b"] = barcode

    product_id = (
        entry.get("retailerProductId")
        or entry.get("productId")
        or entry.get("product_id")
        or entry.get("webshopId")
        or entry.get("sku")
    )
    if product_id not in (None, ""):
        structured["retailerProductId"] = str(product_id).strip()

    product_url = entry.get("productUrl") or entry.get("url") or entry.get("link")
    if product_url:
        structured["productUrl"] = str(product_url).strip()
    image_url = entry.get("imageUrl") or entry.get("image")
    if image_url:
        structured["imageUrl"] = str(image_url).strip()

    brand = entry.get("bn") or entry.get("brand") or entry.get("brandName")
    if isinstance(brand, dict):
        brand = brand.get("name")
    if brand:
        structured["bn"] = str(brand).strip()
        structured["brandSource"] = "retailer"

    sanitized = sanitize_entry(structured)
    return sanitized if sanitized is not None else structured
