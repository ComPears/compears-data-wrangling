"""Extract and normalize EAN/GTIN barcodes from explicit source fields.

Do not scan arbitrary image URLs or free text: numeric runs in CDN hashes and
prices can accidentally pass an EAN checksum and inflate coverage.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
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
    """Return a barcode only when an upstream schema labels it as one."""
    keys = (
        "barcode",
        "barCode",
        "ean",
        "EAN",
        "ean8",
        "ean13",
        "gtin",
        "GTIN",
        "gtin8",
        "gtin12",
        "gtin13",
        "tradeItemNumber",
        "globalTradeItemNumber",
        "b",
    )
    containers = (entry, entry.get("product"), entry.get("attributes"))
    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in keys:
            normalized = normalize_barcode(container.get(key))
            if normalized:
                return normalized

    for key in ("barcodes", "eans", "gtins", "tradeItemNumbers"):
        values = entry.get(key)
        if isinstance(values, Iterable) and not isinstance(values, (str, bytes, dict)):
            for value in values:
                candidate = value.get("value") if isinstance(value, dict) else value
                normalized = normalize_barcode(candidate)
                if normalized:
                    return normalized
    return None
