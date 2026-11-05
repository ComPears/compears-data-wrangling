"""Budgeted optional label refresh. Never changes price catalogs or availability hashes."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from label_evidence import extract_label_evidence
from structured_metadata import _type
from scrape_utils import write_json_atomic
from tls_context import scraper_ssl_context
from ah_api_client import get_anonymous_token, fetch_product_detail
from ah_label_evidence import label_from_ah_detail

ORIGINS = {
    "nl": {"albert-heijn": "https://www.ah.nl", "jumbo": "https://www.jumbo.com", "aldi": "https://www.aldi.nl", "dirk": "https://www.dirk.nl", "plus": "https://www.plus.nl", "lidl": "https://www.lidl.nl", "coop": "https://www.coop.nl"},
    "uk": {"tesco": "https://www.tesco.com", "sainsburys": "https://www.sainsburys.co.uk", "asda": "https://groceries.asda.com", "morrisons": "https://groceries.morrisons.com", "aldi-uk": "https://www.aldi.co.uk", "lidl-uk": "https://www.lidl.co.uk"},
    "de": {"edeka": "https://www.edeka24.de", "rewe": "https://www.rewe.de", "lidl-de": "https://www.lidl.de", "aldi-sud": "https://www.aldi-sued.de", "penny": "https://www.penny.de"},
}


def trusted_url(candidate: str, origin: str) -> str | None:
    try:
        parsed, trusted = urlsplit(candidate), urlsplit(origin)
        if parsed.scheme != "https" or parsed.netloc != trusted.netloc or parsed.username or parsed.password or parsed.path in {"", "/"}:
            return None
        return origin + urlunsplit(("", "", parsed.path, parsed.query, ""))
    except (ValueError, TypeError):
        return None


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, origin): self.origin = origin
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = trusted_url(newurl, self.origin)
        if not url:
            raise urllib.error.HTTPError(req.full_url, code, "Cross-origin redirect rejected", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, url)


class JsonLdScripts(HTMLParser):
    def __init__(self):
        super().__init__(); self.collecting = False; self.chunks = []; self.payloads = []
    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.collecting = True; self.chunks = []
    def handle_data(self, data):
        if self.collecting: self.chunks.append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self.collecting:
            self.collecting = False
            try: self.payloads.append(json.loads("".join(self.chunks)))
            except (ValueError, RecursionError): pass


def evidence_from_html(html: str, url: str, diagnostics: dict | None = None) -> dict | None:
    parser = JsonLdScripts(); parser.feed(html)
    pending = list(parser.payloads); nodes = []; indexed = {}; visited = 0
    def identity(value):
        if isinstance(value, dict): value = value.get('@id')
        if not isinstance(value, str): return None
        try:
            parsed = urlsplit(urljoin(url, value))
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), parsed.query, ''))
        except ValueError:
            return None
    expected = identity(url)
    while pending and visited < 5000:
        node = pending.pop(); visited += 1
        if isinstance(node, dict):
            if isinstance(node.get('@id'), str) and len(node) > 1:
                key = urljoin(url, node['@id'])
                indexed[key] = node if key not in indexed else None  # Reject ambiguous reference targets.
            if _type(node, "Product"):
                node_url = node.get("url") or node.get("@id")
                # Do not attach related products, recipes or another variant's label.
                if identity(node_url) == expected: nodes.append(node)
            pending.extend(v for v in node.values() if isinstance(v, (dict, list)))
        elif isinstance(node, list): pending.extend(node[:5000])
    if len(nodes) != 1:
        if diagnostics is not None: diagnostics['missing-or-ambiguous-product'] = diagnostics.get('missing-or-ambiguous-product', 0) + 1
        return None
    def resolve(value, depth=0):
        if depth >= 3: return value
        if isinstance(value, list): return [resolve(v, depth + 1) for v in value[:100]]
        if isinstance(value, dict) and isinstance(value.get('@id'), str) and len(value) == 1:
            return resolve(indexed.get(urljoin(url, value['@id'])) or {}, depth + 1)
        return value
    product = dict(nodes[0])
    for field in ['nutrition', 'additionalProperty']:
        product[field] = resolve(product.get(field))
    evidence = extract_label_evidence(product, source_url=url)
    if not evidence and diagnostics is not None: diagnostics['product-without-label-facts'] = diagnostics.get('product-without-label-facts', 0) + 1
    return evidence


def fetch_evidence(url: str, origin: str, diagnostics: dict | None = None) -> dict | None:
    def outcome(reason):
        if diagnostics is not None: diagnostics[reason] = diagnostics.get(reason, 0) + 1
    if origin not in {allowed for stores in ORIGINS.values() for allowed in stores.values()}:
        return None
    safe = trusted_url(url, origin)
    if not safe: outcome('invalid-url'); return None
    opener = urllib.request.build_opener(SafeRedirect(origin), urllib.request.HTTPSHandler(context=scraper_ssl_context()))
    request = urllib.request.Request(safe, headers={"User-Agent": "Compears/1.0 product-label research", "Accept": "text/html"})
    try:
        with opener.open(request, timeout=8) as response:
            if "text/html" not in response.headers.get("Content-Type", ""): outcome('not-html'); return None
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000: outcome('oversized'); return None
            final = trusted_url(response.url, origin)
            if final != safe: outcome('redirect-or-variant'); return None  # Needs a dedicated adapter.
            evidence = evidence_from_html(raw.decode("utf-8", errors="replace"), safe, diagnostics)
            if evidence: outcome('json-ld-facts')
            return evidence
    except (OSError, ValueError, urllib.error.URLError):
        outcome('blocked-or-network-error')
        return None


def refresh(root: Path = ROOT, per_store: int = 5, budget_seconds: int = 600) -> dict:
    config = json.loads((root / "config/stores.json").read_text())
    today = datetime.now(timezone.utc).date().isoformat()
    targets = []
    saved = {}
    for country, stores in ORIGINS.items():
        output = root / "label-evidence" / f"{country}.json"
        rows = json.loads(output.read_text()) if output.is_file() else []
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        current = {}
        for row in rows[:10000]:
            try:
                observed = datetime.fromisoformat(row["observedAt"].replace("Z", "+00:00"))
                if cutoff <= observed <= datetime.now(timezone.utc): current[row["sourceUrl"]] = row
            except (KeyError, ValueError, TypeError): pass
        saved[country] = current
        for slug, origin in stores.items():
            store = config["countries"][country]["stores"][slug]
            file = root / store["dir"] / store["catalog"]
            if not file.is_file(): continue
            catalog = json.loads(file.read_text())
            urls = {trusted_url(row.get("productUrl") or row.get("i") or row.get("l") or "", origin) for row in catalog if isinstance(row, dict)}
            ordered = sorted(filter(None, urls), key=lambda u: hashlib.sha256((today + u).encode()).hexdigest())
            for index, url in enumerate(ordered[:max(0, min(per_store, 10))]): targets.append((index, country, slug, origin, url))
    # Round-robin every country/store before taking a second sample from any store.
    targets.sort(key=lambda t: (t[0], hashlib.sha256((today + t[1] + t[2]).encode()).hexdigest()))
    started = time.monotonic(); attempted = found = 0
    diagnostics = {}; ah_token = None; ah_auth_attempted = False
    for _, country, slug, origin, url in targets:
        if time.monotonic() - started >= budget_seconds: break
        attempted += 1
        evidence = None
        ah_id = re.fullmatch(r"/producten/product/wi(\d+)(?:/[^/?#]+)?", urlsplit(url).path) if origin == "https://www.ah.nl" else None
        if ah_id:
            # One public anonymous session, up to the same five daily samples,
            # eight seconds and one attempt per call. Never log or persist tokens.
            try:
                if not ah_auth_attempted:
                    ah_auth_attempted = True
                    ah_token = get_anonymous_token(timeout=8, attempts=1)
                if ah_token:
                    detail = fetch_product_detail(ah_token, ah_id[1], timeout=8, attempts=1, max_response_bytes=1_000_000)
                    evidence = label_from_ah_detail(detail, ah_id[1])
                    if evidence:
                        evidence['sourceUrl'] = url  # Same verified webshopId, exact catalog link.
                        diagnostics['retailer-api-facts'] = diagnostics.get('retailer-api-facts', 0) + 1
            except (OSError, RuntimeError, ValueError, TypeError, AttributeError):
                diagnostics['retailer-api-unavailable'] = diagnostics.get('retailer-api-unavailable', 0) + 1
        if not evidence and time.monotonic() - started < budget_seconds:
            evidence = fetch_evidence(url, origin, diagnostics)
        if evidence: saved[country][url] = evidence; found += 1
        time.sleep(0.25)
    for country, rows in saved.items():
        write_json_atomic(root / "label-evidence" / f"{country}.json", list(rows.values())[:10000])
    return {"attempted": attempted, "found": found, "outcomes": diagnostics, "countries": {country: len(rows) for country, rows in saved.items()}}


if __name__ == "__main__":
    print(json.dumps(refresh(), indent=2))
