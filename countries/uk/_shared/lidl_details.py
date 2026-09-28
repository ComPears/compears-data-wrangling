"""Bounded Lidl pack-size enrichment from explicit, identity-checked PDP text."""

from __future__ import annotations

import re
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

from data_contract import parse_quantity

MAX_PAGE_BYTES = 2 * 1024 * 1024
_SIZE = re.compile(
    r"(?:\d+\s*[x×]\s*)?\d+(?:[.,]\d+)?\s*(?:kg|g|ml|cl|l)"
    r"|\d+\s*(?:pack|pieces|items)", re.I,
)


class _ProductDescription(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.descriptions = []
        self.ids = []
        self.capture = None

    def handle_starttag(self, tag, attrs):
        if tag in {"area", "base", "br", "col", "embed", "hr", "img", "input",
                   "link", "meta", "param", "source", "track", "wbr"}:
            if tag == "br" and self.capture:
                self.capture[2].append("\n")
            return
        self.stack.append(tag)
        attrs = dict(attrs)
        kind = None
        if "short-description__description" in attrs.get("class", "").split():
            kind = "size"
        elif attrs.get("data-qa-label") == "erp-number":
            kind = "id"
        if kind and self.capture is None:
            self.capture = [len(self.stack), kind, []]

    def handle_data(self, data):
        if self.capture:
            self.capture[2].append(data)

    def handle_endtag(self, tag):
        if not self.stack or tag not in self.stack:
            return
        depth = len(self.stack) - self.stack[::-1].index(tag)
        if self.capture and depth <= self.capture[0]:
            _, kind, chunks = self.capture
            (self.ids if kind == "id" else self.descriptions).append("".join(chunks).strip())
            self.capture = None
        del self.stack[depth - 1:]


def size_from_product_html(html: str, product_id: str) -> str | None:
    parser = _ProductDescription()
    parser.feed(html)
    if not parser.ids or set(parser.ids) != {product_id}:
        return None
    sizes = set()
    for text in parser.descriptions:
        # Accept an explicit size, not £/kg, nutrition figures, prose, or
        # alternative variant weights. Never infer pack size from price ratios.
        text = re.sub(r"\s+", " ", text).strip()
        if not _SIZE.fullmatch(text):
            continue
        quantity = parse_quantity(text)
        if quantity:
            sizes.add(str(quantity["display"]))
    return next(iter(sizes)) if len(sizes) == 1 else None


def valid_product_url(url: str, product_id: str) -> bool:
    parsed = urlsplit(url)
    return bool(
        parsed.scheme == "https" and parsed.netloc == "www.lidl.co.uk"
        and re.fullmatch(r"\d+", product_id)
        and re.fullmatch(r"/p/[^/]+/p" + product_id, parsed.path)
        and not parsed.query and not parsed.fragment
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_product_html(url: str, *, timeout: float) -> str:
    # Caller validates an exact retailer host and product ID. Do not follow
    # redirects to other products/hosts or accept unbounded response bodies.
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
    with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
        body = response.read(MAX_PAGE_BYTES + 1)
    if len(body) > MAX_PAGE_BYTES:
        raise ValueError("Lidl product page exceeds size limit")
    return body.decode("utf-8", errors="replace")


def enrich_pack_sizes(rows: list[dict], *, limit: int = 250, budget_seconds: float = 300,
                      fetch=fetch_product_html, clock=time.monotonic) -> dict:
    deadline = clock() + max(0, budget_seconds)
    stats = {"attempted": 0, "enriched": 0, "unavailable": 0}
    cache = {}
    for row in rows:
        if parse_quantity(row.get("s") or ""):
            continue
        url = str(row.get("productUrl") or row.get("i") or "")
        product_id = str(row.get("retailerProductId") or "")
        if not valid_product_url(url, product_id):
            continue
        if url not in cache:
            remaining = deadline - clock()
            if stats["attempted"] >= limit or remaining <= 0:
                break
            stats["attempted"] += 1
            try:
                cache[url] = size_from_product_html(fetch(url, timeout=min(8, remaining)), product_id)
            except (OSError, ValueError):
                cache[url] = None
            if not cache[url]:
                stats["unavailable"] += 1
        if cache[url]:
            row["s"] = cache[url]
            row["quantitySource"] = "retailer_product_description"
            row["quantitySourceUrl"] = url
            row["quantityObservedAt"] = datetime.now(timezone.utc).isoformat()
            stats["enriched"] += 1
        if stats["attempted"] % 25 == 0:
            print(f"Lidl package-size enrichment: {stats}", flush=True)
    print(f"Lidl package-size enrichment complete: {stats}", flush=True)
    return stats
