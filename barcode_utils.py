"""Extract and normalize EAN/GTIN barcodes from scrape fields."""

from __future__ import annotations

import re
from typing import Any

# Dutch retail GTINs often start with 87; also match 13-digit EAN in URLs/filenames.
_EAN_CANDIDATE = re.compile(r"(?<!\d)(0?87\d{11}|\d{13}|\d{8})(?!\d)")


def _checksum_ean13(digits: str) -> bool:
    if len(digits) != 13 or not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(digits[:12]):
        n = int(ch)
        total += n * (1 if i % 2 == 0 else 3)
    check = (10 - (total % 10)) % 10
    return check == int(digits[12])


def _checksum_ean8(digits: str) -> bool:
    if len(digits) != 8 or not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(digits[:7]):
        n = int(ch)
        total += n * (3 if i % 2 == 0 else 1)
    check = (10 - (total % 10)) % 10
    return check == int(digits[7])


def normalize_barcode(raw: str | int | None) -> str | None:
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw).strip())
    if len(digits) == 12:
        digits = f"0{digits}"
    if len(digits) == 13 and _checksum_ean13(digits):
        return digits
    if len(digits) == 8 and _checksum_ean8(digits):
        return digits
    return None


def extract_barcode_from_text(text: str | None) -> str | None:
    if not text:
        return None
    for match in _EAN_CANDIDATE.finditer(text):
        candidate = normalize_barcode(match.group(1))
        if candidate:
            return candidate
    return None


def extract_barcode_from_entry(entry: dict[str, Any]) -> str | None:
    for key in ("barcode", "ean", "gtin", "b"):
        if key in entry:
            normalized = normalize_barcode(entry.get(key))
            if normalized:
                return normalized

    for key in ("link", "image", "l", "i", "product_url", "raw_text"):
        value = entry.get(key)
        if isinstance(value, str):
            found = extract_barcode_from_text(value)
            if found:
                return found
    return None
