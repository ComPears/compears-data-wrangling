"""EAN extraction from Dirk product-card source schema and PDP JSON-LD."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin

from barcode_utils import extract_barcode_from_entry, extract_barcode_from_html, extract_barcode_from_json_ld

DIRK_ORIGIN = "https://www.dirk.nl"
DEFAULT_PDP_ENRICH_LIMIT = 800
DEFAULT_PDP_WORKERS = 2
PDP_ENRICH_DELAY = 0.25
DIRK_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def extract_card_barcode(card: Any) -> str | None:
    """Read explicit data attributes and Product JSON-LD from a Dirk card."""
    explicit = {
        "ean": card.get_attribute("data-ean"),
        "gtin": card.get_attribute("data-gtin"),
        "barcode": card.get_attribute("data-product-ean"),
    }
    barcode = extract_barcode_from_entry(explicit)
    if barcode:
        return barcode

    for script in card.query_selector_all('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.text_content() or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) or isinstance(payload, list):
            barcode = extract_barcode_from_json_ld(payload)
            if barcode:
                return barcode
    return None


def extract_card_link(card: Any) -> str | None:
    """Return an absolute product URL from a listing card, if present."""
    link_el = None
    for selector in ("a[href*='/producten/']", "a[href*='/product/']", "a[href]"):
        link_el = card.query_selector(selector)
        if link_el:
            break
    if not link_el:
        return None
    href = link_el.get_attribute("href")
    if not href:
        return None
    return urljoin(DIRK_ORIGIN, href)


def extract_pdp_barcode(html_or_json: str | dict | list | None) -> str | None:
    """Find Product JSON-LD gtin/gtin13/ean on a Dirk PDP (HTML or parsed JSON)."""
    if html_or_json is None:
        return None
    if isinstance(html_or_json, (dict, list)):
        return extract_barcode_from_json_ld(html_or_json)
    text = str(html_or_json)
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            barcode = extract_barcode_from_json_ld(payload)
            if barcode:
                return barcode
    return extract_barcode_from_html(text)


def _fetch_html(url: str, *, timeout: int = 30) -> str | None:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": DIRK_USER_AGENT, "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def enrich_dirk_entries_with_pdp_barcodes(
    entries: list[dict],
    *,
    limit: int = DEFAULT_PDP_ENRICH_LIMIT,
    workers: int = DEFAULT_PDP_WORKERS,
) -> int:
    """Visit product pages for cards missing barcode. Returns number enriched."""
    if limit <= 0:
        return 0

    targets: list[tuple[int, str]] = []
    for index, entry in enumerate(entries):
        if entry.get("barcode"):
            continue
        link = entry.get("link")
        if not link:
            continue
        targets.append((index, str(link)))
        if len(targets) >= limit:
            break

    if not targets:
        return 0

    enriched = 0
    workers = max(1, min(workers, 3))

    def _lookup(url: str) -> str | None:
        try:
            html = _fetch_html(url)
            time.sleep(PDP_ENRICH_DELAY)
            return extract_pdp_barcode(html)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_lookup, url): index for index, url in targets}
        for future in as_completed(futures):
            index = futures[future]
            try:
                barcode = future.result()
            except Exception:
                continue
            if barcode:
                entries[index]["barcode"] = barcode
                enriched += 1

    return enriched
