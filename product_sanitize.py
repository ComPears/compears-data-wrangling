"""Shared product sanitization: names, sizes, brand, identity keys, rejection rules."""

from __future__ import annotations

import re
from typing import Any

from barcode_utils import extract_barcode_from_entry, normalize_barcode

# --- rejection: promo banners / junk rows (Lidl, PLUS, etc.) ---

REJECT_NAME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"prijsvoorbeeld", re.I),
    re.compile(r"actieprijzen\s+vari", re.I),
    re.compile(r"in verschillende varianten", re.I),
    re.compile(r"\ball[e]?\s+.+\s+voor\b", re.I),
    re.compile(r"\bvanaf\s*-?\d+\s*%", re.I),
    re.compile(r"alleen in de winkel vanaf", re.I),
    re.compile(r"^\s*bij\s*$", re.I),
    re.compile(r"^\s*bij\s+\d", re.I),
    re.compile(r"^\d+[.,]\d{2}\s*(euro|eur)?\s*$", re.I),
    re.compile(r"^nu voor\b", re.I),
]

PROMO_IN_NAME_FRAGMENTS: tuple[str, ...] = (
    "vanaf -",
    "vanaf ",
    "prijsvoorbeeld",
    "actieprijzen",
    "alleen in de winkel",
    "met lidl plus",
    "voor eur ",
    " in verschillende varianten",
    "goedkoper",
)

GENERIC_STOPWORDS: frozenset[str] = frozenset(
    {
        "per",
        "stuk",
        "stuks",
        "st",
        "st.",
        "voor",
        "eur",
        "euro",
        "de",
        "het",
        "een",
        "en",
        "met",
        "van",
        "voordeel",
        "voordeelverpakking",
        "voordeelpak",
        "verpakking",
        "pak",
        "nieuw",
        "prijs",
        "actie",
        "aanbieding",
        "gratis",
        "op=op",
        "online",
        "alleen",
        "winkel",
    }
)

STORE_TOKENS: frozenset[str] = frozenset(
    {
        "ah",
        "jumbo",
        "plus",
        "dirk",
        "lidl",
        "aldi",
        "coop",
        "huismerk",
        "1e",
        "prijs",
    }
)

KNOWN_BRANDS: frozenset[str] = frozenset(
    {
        "campina",
        "melkunie",
        "arla",
        "optimel",
        "sensodyne",
        "prodent",
        "aquafresh",
        "signal",
        "colgate",
        "milka",
        "cote",
        "dor",
        "unox",
        "knorr",
        "maggi",
        "heinz",
        "calve",
        "honig",
        "jumbo",
        "ah",
        "plus",
        "coca",
        "cola",
        "pepsi",
        "fanta",
        "spa",
        "heineken",
        "amstel",
        "grolsch",
        "douwe",
        "egberts",
        "lavazza",
        "nescafe",
        "bolletje",
        "wasa",
        "lu",
        "bastogne",
        "hero",
        "bonduelle",
        "iglo",
        "ola",
        "ben",
        "jerry",
        "hak",
        "grand",
        "italia",
        "mutti",
        "barilla",
        "nivea",
        "dove",
        "axe",
        "gillette",
        "always",
        "libresse",
        "pampers",
        "nappy",
        "nutrilon",
        "friso",
        "babybel",
        "philadelphia",
        "boursin",
        "galbani",
        "leerdammer",
        "old",
        "amsterdam",
        "liga",
        "sportlife",
        "redband",
        "mars",
        "snickers",
        "twix",
        "haribo",
        "red",
        "bull",
        "innocent",
    }
)

# Multi-word brands checked before single token
MULTI_WORD_BRANDS: tuple[str, ...] = (
    "cote d or",
    "côte d or",
    "douwe egberts",
    "old amsterdam",
    "red bull",
    "ben jerry",
    "ben & jerry",
    "grand italia",
    "la vache qui rit",
)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def should_reject_name(name: str) -> str | None:
    """Return rejection reason or None if acceptable (hard junk only)."""
    n = _collapse_ws(name)
    if len(n) < 3:
        return "name_too_short"
    for pattern in REJECT_NAME_PATTERNS:
        if pattern.search(n):
            return f"reject_pattern:{pattern.pattern[:40]}"
    return None


def strip_promo_from_name(name: str) -> str:
    text = name
    for frag in PROMO_IN_NAME_FRAGMENTS:
        idx = text.lower().find(frag)
        if idx >= 0:
            text = text[:idx]
    text = re.sub(r"\bvoor\s+met\s+lidl\s+plus\b.*$", "", text, flags=re.I)
    text = re.sub(r"\bvoor\s+eur\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s*-\d+\s*%\s*$", "", text)
    text = re.sub(r"\b\d+\s*%\s*korting\b", "", text, flags=re.I)
    text = re.sub(r"\b2e\s+halve\s+prijs\b", "", text, flags=re.I)
    text = re.sub(r"\b1\s*\+\s*1\s*gratis\b", "", text, flags=re.I)
    text = re.sub(r"\s+voor\s*$", "", text, flags=re.I)
    return _collapse_ws(text)


def parse_size_to_ml(size: str | None) -> int | None:
    if not size:
        return None
    lower = size.lower().replace(",", ".")
    lower = re.sub(r"^per\s+", "", lower)

    multi = re.search(r"(\d+)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(ml|l|g|kg)\b", lower)
    if multi:
        count = int(multi.group(1))
        qty = float(multi.group(2))
        unit = multi.group(3)
        if unit == "l":
            return int(round(count * qty * 1000))
        if unit == "ml":
            return int(round(count * qty))
        if unit == "kg":
            return int(round(count * qty * 1000))
        if unit == "g":
            return int(round(count * qty))

    ml_match = re.search(r"(\d+(?:\.\d+)?)\s*ml\b", lower)
    if ml_match:
        return int(round(float(ml_match.group(1))))

    l_match = re.search(r"(\d+(?:\.\d+)?)\s*l(?:iter)?(?!\w)", lower)
    if l_match:
        return int(round(float(l_match.group(1)) * 1000))

    g_match = re.search(r"(\d+(?:\.\d+)?)\s*g(?:ram)?(?!\w)", lower)
    if g_match:
        return int(round(float(g_match.group(1))))

    kg_match = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", lower)
    if kg_match:
        return int(round(float(kg_match.group(1)) * 1000))

    st_match = re.search(r"(\d+)\s*st(?:uk)?(?:s)?\b", lower)
    if st_match:
        return int(st_match.group(1))

    if lower in {"stuk", "st", "st.", "per stuk"}:
        return 1

    return None


def normalize_size_label(size: str | None, size_ml: int | None) -> str:
    if size_ml is not None:
        if size_ml >= 1000 and size_ml % 1000 == 0:
            return f"{size_ml // 1000} l"
        if size_ml >= 1000:
            return f"{size_ml / 1000:.2f} l".replace(".00", "")
        if size_ml == 1:
            return "1 stuk"
        return f"{size_ml} ml"
    return _collapse_ws(size or "stuk")


def extract_brand(name: str) -> str | None:
    lower = name.lower()
    for phrase in MULTI_WORD_BRANDS:
        if phrase in lower:
            return _collapse_ws(phrase)
    tokens = re.findall(r"[a-z0-9&]+", lower)
    for token in tokens:
        if token in KNOWN_BRANDS:
            return token
    # First capitalized word often brand in Dutch listings
    for word in name.split():
        clean = re.sub(r"[^a-zA-Z&]", "", word)
        if len(clean) >= 3 and clean[0].isupper() and clean.lower() not in GENERIC_STOPWORDS:
            return clean.lower()
    return None


def tokenize_product_name(name: str, brand: str | None) -> list[str]:
    lower = name.lower()
    if brand:
        for part in brand.lower().split():
            lower = re.sub(rf"\b{re.escape(part)}\b", " ", lower)
    lower = re.sub(r"\d+(?:[.,]\d+)?\s*(ml|l|cl|g|kg|stuks?|st)\b", " ", lower)
    tokens = re.findall(r"[a-z0-9]+", lower)
    result: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in GENERIC_STOPWORDS or token in STORE_TOKENS:
            continue
        if len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            result.append(token)
    result.sort()
    return result


def build_canonical_name(name: str, brand: str | None, tokens: list[str]) -> str:
    if brand and tokens:
        return f"{brand} {' '.join(tokens)}"
    if tokens:
        return " ".join(tokens)
    return _collapse_ws(name).lower()


def title_case_canonical(cn: str) -> str:
    return " ".join(w.capitalize() if w.isalpha() else w for w in cn.split())


def build_identity_key(
    *,
    barcode: str | None,
    brand: str | None,
    tokens: list[str],
    size_ml: int | None,
) -> str:
    if barcode:
        return f"ean:{barcode}"
    token_part = "-".join(tokens) if tokens else "unknown"
    brand_part = brand or "unknown"
    size_part = str(size_ml) if size_ml is not None else "na"
    return f"tok:{brand_part}|{token_part}|{size_part}"


def sanitize_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Return sanitized entry or None if row should be rejected."""
    raw_name = str(entry.get("n") or "").strip()
    if not raw_name:
        return None

    clean_name = strip_promo_from_name(raw_name)
    if len(clean_name) < 3:
        return None

    reject = should_reject_name(clean_name)
    if reject:
        return None

    barcode = extract_barcode_from_entry(entry)
    brand = entry.get("bn") or extract_brand(clean_name)
    if isinstance(brand, str):
        brand = brand.strip().lower() or None

    size_raw = str(entry.get("s") or "").strip()
    size_ml = entry.get("wg")
    if size_ml is not None:
        try:
            size_ml = int(size_ml)
        except (TypeError, ValueError):
            size_ml = None
    if size_ml is None:
        size_ml = parse_size_to_ml(size_raw)

    tokens = tokenize_product_name(clean_name, brand)
    if not tokens and not brand:
        return None

    cn = build_canonical_name(clean_name, brand, tokens)
    ik = build_identity_key(barcode=barcode, brand=brand, tokens=tokens, size_ml=size_ml)

    out = dict(entry)
    out["n"] = title_case_canonical(clean_name) if clean_name else clean_name
    out["cn"] = cn
    out["ik"] = ik
    if brand:
        out["bn"] = brand
    if size_ml is not None:
        out["wg"] = size_ml
    out["s"] = normalize_size_label(size_raw, size_ml)
    if barcode:
        out["b"] = barcode
    return out


def _parse_price(value: Any) -> float:
    s = str(value or "").strip().replace(",", ".")
    if not s:
        return float("inf")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return float("inf")
    try:
        return float(m.group(0))
    except ValueError:
        return float("inf")


def dedupe_by_identity(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep cheapest price per identity key (ik)."""
    best: dict[str, dict[str, Any]] = {}
    removed = 0
    for item in items:
        key = item.get("ik") or item.get("cn") or item.get("n")
        if not key:
            continue
        price = _parse_price(item.get("p"))
        existing = best.get(str(key))
        if existing is None:
            best[str(key)] = item
            continue
        ex_price = _parse_price(existing.get("p"))
        if price < ex_price:
            best[str(key)] = item
        removed += 1
    return list(best.values()), removed
