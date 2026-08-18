"""Shared product sanitization: names, sizes, brand, identity keys, rejection rules."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from barcode_utils import extract_barcode_from_entry, normalize_barcode
from data_contract import (
    SCHEMA_VERSION,
    normalize_price,
    parse_quantity,
    quantity_fingerprint,
    resolve_urls,
    unit_price,
    utc_iso,
)
from product_relevance import rejection_reason as relevance_rejection_reason

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
        "unox",
        "knorr",
        "maggi",
        "heinz",
        "calve",
        "honig",
        "jumbo",
        "ah",
        "plus",
        "pepsi",
        "fanta",
        "spa",
        "heineken",
        "amstel",
        "grolsch",
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
        "hak",
        "mutti",
        "barilla",
        "nivea",
        "dove",
        "axe",
        "gillette",
        "always",
        "libresse",
        "pampers",
        "nutrilon",
        "friso",
        "babybel",
        "philadelphia",
        "boursin",
        "galbani",
        "leerdammer",
        "liga",
        "sportlife",
        "redband",
        "mars",
        "snickers",
        "twix",
        "haribo",
        "innocent",
    }
)

# Multi-word brands checked before single tokens. Canonical values keep
# punctuation variants from fragmenting otherwise valid comparison groups.
MULTI_WORD_BRANDS: tuple[tuple[str, str], ...] = (
    ("cote d or", "côte d'or"),
    ("côte d or", "côte d'or"),
    ("coca cola", "coca-cola"),
    ("douwe egberts", "douwe egberts"),
    ("old amsterdam", "old amsterdam"),
    ("red bull", "red bull"),
    ("ben jerry", "ben & jerry"),
    ("ben and jerry", "ben & jerry"),
    ("grand italia", "grand italia"),
    ("la vache qui rit", "la vache qui rit"),
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
    """Backward-compatible numeric quantity; use ``parse_quantity`` for units."""
    parsed = parse_quantity(size)
    if not parsed:
        return None
    value = parsed.get("totalValue")
    return int(value) if isinstance(value, (int, float)) else None


def normalize_size_label(size: str | None, size_ml: int | None) -> str:
    """Preserve the source unit instead of labelling every quantity as volume."""
    parsed = parse_quantity(size)
    if parsed:
        return str(parsed["display"])
    return _collapse_ws(size or "")


def extract_brand(name: str) -> str | None:
    lower = name.lower()
    normalized = _collapse_ws(re.sub(r"[^\w]+", " ", lower, flags=re.UNICODE))
    for alias, canonical in MULTI_WORD_BRANDS:
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return canonical
    tokens = re.findall(r"[a-z0-9&]+", lower)
    for token in tokens:
        if token in KNOWN_BRANDS:
            return token
    # Do not infer arbitrary capitalized words as brands. A missing brand is
    # safer than a false brand because brand participates in automatic matching.
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
    size_ml: int | None = None,
    quantity: dict[str, Any] | None = None,
) -> str:
    if barcode:
        return f"ean:{barcode}"
    token_part = "-".join(tokens) if tokens else "unknown"
    brand_part = brand or "unknown"
    size_part = quantity_fingerprint(quantity)
    if size_part == "na" and size_ml is not None:
        size_part = str(size_ml)
    return f"tok:{brand_part}|{token_part}|{size_part}"


def sanitize_entry_with_reason(
    entry: dict[str, Any],
    *,
    country: str | None = None,
    store: str | None = None,
    currency: str | None = None,
    observed_at: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return a contract-compliant offer and a machine-readable rejection reason."""
    raw_name = str(entry.get("n") or "").strip()
    if not raw_name:
        return None, "missing_name"

    clean_name = strip_promo_from_name(raw_name)
    if len(clean_name) < 3:
        return None, "name_too_short"

    reject = should_reject_name(clean_name)
    if reject:
        return None, reject

    size_raw = str(entry.get("s") or "").strip()
    quantity = parse_quantity(
        size_raw,
        name=clean_name,
        existing=entry.get("quantity") if isinstance(entry.get("quantity"), dict) else None,
    )

    # Resolve the category before the relevance gate so store-specific filters
    # can distinguish a comparable grocery row from an ambiguous non-food row.
    # The lazy import avoids a module cycle with category_utils' sanitizer hook.
    from category_utils import ensure_canonical, infer_category_from_name

    category = ensure_canonical(str(entry.get("c") or entry.get("category") or ""))
    if category == "Other":
        inferred_category = infer_category_from_name(clean_name)
        if inferred_category != "Other":
            category = inferred_category

    relevance_reject = relevance_rejection_reason(
        clean_name,
        country,
        store=store,
        category=category,
        has_quantity=bool(quantity),
    )
    if relevance_reject:
        return None, relevance_reject

    price_ceiling = Decimal("100.00") if country == "uk" else Decimal("500.00")
    price, price_error = normalize_price(entry.get("p"), maximum=price_ceiling)
    if price_error:
        return None, price_error

    barcode = extract_barcode_from_entry(entry)
    inferred_brand = extract_brand(clean_name)
    raw_brand = entry.get("bn")
    raw_brand = raw_brand.strip().lower() if isinstance(raw_brand, str) else None
    raw_brand_source = str(entry.get("brandSource") or "").strip().lower()
    trusted_brand_sources = {"retailer", "gtin", "known_name"}
    if raw_brand and raw_brand_source in trusted_brand_sources:
        brand = raw_brand
        brand_source = raw_brand_source
    elif raw_brand and inferred_brand and raw_brand == inferred_brand:
        brand = raw_brand
        brand_source = "known_name"
    else:
        brand = inferred_brand
        brand_source = "known_name" if inferred_brand else None

    tokens = tokenize_product_name(clean_name, brand)
    if not tokens and not brand:
        return None, "missing_identity_attributes"

    cn = build_canonical_name(clean_name, brand, tokens)
    ik = build_identity_key(barcode=barcode, brand=brand, tokens=tokens, quantity=quantity)

    out = dict(entry)
    out["n"] = title_case_canonical(clean_name) if clean_name else clean_name
    out["p"] = price
    offer_text = str(out.get("o") or "").strip()
    if re.search(r"\b(clubcard|nectar price)\b", offer_text, re.I):
        out["priceType"] = "loyalty"
    elif offer_text:
        out["priceType"] = "promotion"
    else:
        out["priceType"] = "regular"
    out["cn"] = cn
    out["ik"] = ik
    out["schemaVersion"] = SCHEMA_VERSION
    if brand:
        out["bn"] = brand
        out["brandSource"] = brand_source
    else:
        out.pop("bn", None)
        out.pop("brandSource", None)
    if quantity:
        out["quantity"] = quantity
        out["wg"] = quantity["totalValue"]
        out["wu"] = quantity["baseUnit"]
        out["s"] = quantity["display"]
    else:
        out.pop("quantity", None)
        out.pop("wg", None)
        out.pop("wu", None)
        out["s"] = _collapse_ws(size_raw)
    if barcode:
        out["b"] = barcode
    else:
        out.pop("b", None)

    out["c"] = category

    resolved_currency = (currency or entry.get("currency") or "").upper()
    if not resolved_currency:
        resolved_currency = {"nl": "EUR", "de": "EUR", "uk": "GBP"}.get(country or "", "")
    if country:
        out["country"] = country
    if store:
        out["retailer"] = store
    if resolved_currency:
        out["currency"] = resolved_currency
    computed_unit_price = unit_price(price, resolved_currency, quantity) if resolved_currency else None
    if computed_unit_price:
        out["unitPrice"] = computed_unit_price
    else:
        out.pop("unitPrice", None)

    product_url, image_url = resolve_urls(out)
    if product_url:
        out["productUrl"] = product_url
    else:
        out.pop("productUrl", None)
    if image_url:
        out["imageUrl"] = image_url
    else:
        out.pop("imageUrl", None)

    timestamp = utc_iso(observed_at) or utc_iso(
        entry.get("observedAt") or entry.get("scrapedAt") or entry.get("scraped_at")
    )
    if timestamp:
        out["observedAt"] = timestamp
    return out, None


def sanitize_entry(
    entry: dict[str, Any],
    *,
    country: str | None = None,
    store: str | None = None,
    currency: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any] | None:
    """Compatibility wrapper returning only the sanitized offer."""
    cleaned, _reason = sanitize_entry_with_reason(
        entry,
        country=country,
        store=store,
        currency=currency,
        observed_at=observed_at,
    )
    return cleaned


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
