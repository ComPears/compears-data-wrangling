"""Decode Dirk's separate euro/cent card lines before normalization."""
import re
from decimal import Decimal


def card_price(parts: list[str]) -> str:
    if len(parts) == 1 and re.fullmatch(r"\d{1,2}", parts[0]):
        return f"{Decimal(parts[0]) / 100:.2f}"
    if len(parts) == 2 and re.fullmatch(r"\d{1,4}", parts[0]) and re.fullmatch(r"\d{2}", parts[1]):
        return f"{Decimal(parts[0] + '.' + parts[1]):.2f}"
    return ""  # Do not guess when the price block has an unexpected shape.


def metadata_row(**product):
    return product


def corroborate_card(entry: dict, metadata: list[dict]) -> dict:
    matches = [item for item in metadata if item.get("url") == entry.get("link")]
    lines = [line.strip() for line in entry["raw_text"].splitlines() if line.strip()]
    parts = []
    while lines and lines[0].isdigit():
        parts.append(lines.pop(0))
    price = card_price(parts)
    if len(matches) == 1 and price and price == matches[0].get("price"):
        item = matches[0]
        entry["sourceMethod"] = "dom_cards_json_ld"
        if not entry.get("barcode") and item.get("barcode"):
            entry["barcode"] = item["barcode"]
    else:
        entry["sourceMethod"] = "dom_cards"
    return entry
