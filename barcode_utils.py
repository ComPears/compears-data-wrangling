"""Extract and normalize EAN/GTIN barcodes from explicit source fields.

Do not scan arbitrary image URLs or free text: numeric runs in CDN hashes and
prices can accidentally pass an EAN checksum and inflate coverage.

Store-specific enrichment paths (AH detail API, PLUS PDP/Next data, Dirk PDP
JSON-LD) feed named GTIN/EAN fields into ``extract_barcode_from_entry``. Jumbo
DAM URLs may embed real EANs, but only the backend Jumbo-safe URL miner (or an
explicit ``b`` / ``barcode`` field) should consume those.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

# Dutch retail GTINs often start with 87; also match 13-digit EAN in URLs/filenames.
_EAN_CANDIDATE = re.compile(r"(?<!\d)(0?87\d{11}|\d{13}|\d{8})(?!\d)")
_LD_JSON_SCRIPT = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_NEXT_DATA_SCRIPT = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


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
    # GTIN-14 (often leading indicator/zero) → EAN-13
    if len(digits) == 14 and digits.startswith("0"):
        digits = digits[1:]
    elif len(digits) > 13:
        stripped = digits.lstrip("0")
        if len(stripped) in (8, 13):
            digits = stripped
        elif len(stripped) == 12:
            digits = f"0{stripped}"
        else:
            digits = digits[-13:]
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
        "gtin14",
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


def barcode_from_product_code(raw: str | int | None) -> str | None:
    """Accept Product_Code only when it checksum-validates as a real-looking GTIN.

    Short PLUS internal IDs that happen to pad into a checksum-valid EAN-13 are
    rejected; Dutch retail GTINs (``87…``) and other full-length source strings
    (≥12 digit chars before padding) are kept.
    """
    if raw is None:
        return None
    source = re.sub(r"\D", "", str(raw).strip())
    normalized = normalize_barcode(source)
    if not normalized:
        return None
    if normalized.startswith("87"):
        return normalized
    if len(source) >= 12:
        return normalized
    return None


def _iter_json_nodes(payload: Any) -> Iterable[Any]:
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_json_nodes(item)
        return
    if not isinstance(payload, dict):
        return
    yield payload
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _iter_json_nodes(item)
    for key in ("product", "mainEntity", "item"):
        nested = payload.get(key)
        if isinstance(nested, (dict, list)):
            yield from _iter_json_nodes(nested)


def _is_product_type(node: dict[str, Any]) -> bool:
    type_value = node.get("@type")
    if isinstance(type_value, list):
        return any(str(item).lower() == "product" for item in type_value)
    return str(type_value or "").lower() == "product"


def extract_barcode_from_json_ld(payload: Any) -> str | None:
    """Find gtin/ean on Product JSON-LD nodes (dict, list, or @graph)."""
    for node in _iter_json_nodes(payload):
        if not isinstance(node, dict):
            continue
        if node.get("@type") is not None and not _is_product_type(node):
            continue
        barcode = extract_barcode_from_entry(node)
        if barcode:
            return barcode
    return None


def extract_barcode_from_next_data(payload: Any) -> str | None:
    """Walk Next.js ``__NEXT_DATA__`` for named EAN/GTIN fields."""
    stack: list[Any] = [payload]
    seen = 0
    while stack and seen < 5000:
        current = stack.pop()
        seen += 1
        if isinstance(current, dict):
            barcode = extract_barcode_from_entry(current)
            if barcode:
                return barcode
            # Product_Code on PDP detail only when it looks like a real GTIN.
            code = barcode_from_product_code(current.get("Product_Code") or current.get("productCode"))
            if code:
                return code
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return None


def extract_barcode_from_html(html: str | None) -> str | None:
    """Extract barcode from Product JSON-LD or ``__NEXT_DATA__`` embedded in HTML."""
    if not html:
        return None

    for match in _LD_JSON_SCRIPT.finditer(html):
        raw = (match.group(1) or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        barcode = extract_barcode_from_json_ld(payload)
        if barcode:
            return barcode

    next_match = _NEXT_DATA_SCRIPT.search(html)
    if next_match:
        raw = (next_match.group(1) or "").strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            barcode = extract_barcode_from_next_data(payload)
            if barcode:
                return barcode

    return None
