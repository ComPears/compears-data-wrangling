"""Conservative filters for durable goods leaked by supermarket search pages."""

from __future__ import annotations

import re


_DURABLE_GOOD_PHRASES: dict[str, tuple[str, ...]] = {
    "nl": (
        "parkside",
        "ultimate speed",
        "crivit",
        "tronic",
        "livarno",
        "esmara",
        "silvercrest",
        "byliving",
        "dirt devil",
        "eisl ",
        "gözze",
        "güde",
        "kleine wolke",
        "osann",
        "ridder ",
        "schildmeyer",
        "schütte",
        "wenko",
        "accuboormachine",
        "airco",
        "autostoel",
        "badkamerkast",
        "badkamerkraan",
        "badmat",
        "badjas",
        "dakdrager",
        "damessok",
        "fiets",
        "gereedschap",
        "hydraulische krik",
        "handdoek",
        "herensok",
        "koffiebereider",
        "boormachine",
        "hogedrukreiniger",
        "motorhelm",
        "oven met kookplaat",
        "prullenbak",
        "regenjas",
        "sauna",
        "schoen",
        "scooter helm",
        "spiegel",
        "telefoonhouder",
        "terrasoverkapping",
        "thuisbatterij",
        "toiletborstel",
        "toiletrolhouder",
        "wastafelkraan",
        "wasmand",
        "zeepdispenser",
        "koffiemachine",
        "keukenmachine",
        "nachtlamp",
        "opbergbox",
        "traphekje",
        "vliesbehang",
        "laptop",
        "luchtfriteuse",
        "matras",
        "smartphone",
        "stofzuiger",
        "televisie",
        "wasmachine",
    ),
    "de": (
        "ambiano",
        "parkside",
        "silvercrest",
        "akkuschrauber",
        "bettwäsche",
        "bit-box",
        "bitkassette",
        "bohrerbox",
        "bohrmaschine",
        "deko-figur",
        "eiscrusher",
        "eiswürfelform",
        "espressokocher",
        "fernseher",
        "hochdruckreiniger",
        "kaffeebereiter",
        "kaffeepadmaschine",
        "kaffeevollautomat",
        "kaffeemaschine",
        "küchenmaschine",
        "handmixer",
        "laptop",
        "luftfritteuse",
        "matratze",
        "milchaufschäumer",
        "milchtopf",
        "milbensauger",
        "puppe",
        "rasenmäher",
        "smartphone",
        "staubsauger",
        "teppich",
        "teebereiter",
        "trinkflasche",
        "waffeleisen",
        "waschmaschine",
    ),
    "uk": (
        "ambiano",
        "parkside",
        "silvercrest",
        "air fryer",
        "bento box",
        "bento cube",
        "coffee machine",
        "cordless drill",
        "dishwasher",
        "laptop",
        "lawn mower",
        "mattress",
        "milk frother",
        "milk pan",
        "pressure washer",
        "espresso machine",
        "frying pan",
        "microwave",
        "pet bed",
        "replacement bags",
        "smartphone",
        "tablecloth",
        "toaster",
        "television",
        "tumble dryer",
        "vacuum cleaner",
        "washing machine",
        "whisk",
    ),
}

_NAVIGATION_NAMES = re.compile(
    r"^(products?|groceries|angebote|sortiment|top angebote|search results?|"
    r"all products?|view all|mehr anzeigen|alle anzeigen)$",
    re.IGNORECASE,
)

_LIDL_STORES = frozenset({"lidl", "lidl-de", "lidl-uk"})
_AMBIGUOUS_WITHOUT_QUANTITY = frozenset({"Other", "Personal Care", "Household"})


def rejection_reason(
    name: str,
    country: str | None,
    *,
    store: str | None = None,
    category: str | None = None,
    has_quantity: bool = True,
) -> str | None:
    """Return a reason only for high-confidence non-offer or durable-goods rows."""
    normalized = re.sub(r"\s+", " ", str(name or "").strip().lower())
    if _NAVIGATION_NAMES.fullmatch(normalized):
        return "navigation_row"
    phrases = _DURABLE_GOOD_PHRASES.get(str(country or "").lower(), ())
    if any(phrase in normalized for phrase in phrases):
        return "durable_non_grocery"
    # Lidl search pages mix groceries with a large rotating non-food catalogue.
    # Rows in these broad categories are not safely comparable without package
    # evidence, so quarantine them instead of inflating the grocery catalogue.
    if (
        str(store or "").lower() in _LIDL_STORES
        and not has_quantity
        and str(category or "Other") in _AMBIGUOUS_WITHOUT_QUANTITY
    ):
        return "ambiguous_lidl_non_grocery"
    return None
