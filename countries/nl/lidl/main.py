import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import sync_playwright

from links import (
    FALLBACK_LEAF_URLS,
    MAX_OFFSET,
    OFFSET_STEP,
    SEED_CATEGORY_URLS,
    SKIP_MAIN_SLUGS,
)


def _repo_root():
    from pathlib import Path
    import sys

    p = Path(__file__).resolve().parent
    for _ in range(8):
        if (p / "config" / "stores.json").is_file():
            s = str(p)
            if s not in sys.path:
                sys.path.insert(0, s)
            return p
        p = p.parent
    raise RuntimeError("Could not find compears-data-wrangling root")


_repo_root()
from category_utils import category_from_url
from scrape_utils import (
    accept_common_cookies,
    configure_page,
    goto_resilient,
    launch_browser,
    report_batch_failures,
    require_products,
    wait_for_products,
)

LEAF_RE = re.compile(r"/h/([a-z0-9-]+)/(h\d+)", re.I)
MAIN_RE = re.compile(r"/c/([a-z0-9-]+)/(s\d+)", re.I)


def _leaf_slug(url: str) -> str | None:
    match = LEAF_RE.search(url)
    return match.group(1).lower() if match else None


def _canonical_leaf_url(url: str) -> str | None:
    match = LEAF_RE.search(url)
    if not match:
        return None
    return f"https://www.lidl.nl/h/{match.group(1)}/{match.group(2)}"


def _with_offset(url: str, offset: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if offset <= 0:
        query.pop("offset", None)
    else:
        query["offset"] = [str(offset)]
    flat = {key: values[0] for key, values in query.items()}
    return urlunparse(parsed._replace(query=urlencode(flat)))


def discover_leaf_urls(page) -> list[str]:
    """Collect leaf `/h/...` URLs from all shop main departments."""
    found: dict[str, str] = {}
    seeds = list(SEED_CATEGORY_URLS)

    # Also pick up any other product mains linked from the homepage.
    print("🔎 Discovering Lidl mains from homepage")
    goto_resilient(page, "https://www.lidl.nl/")
    page.wait_for_timeout(2000)
    accept_common_cookies(page)
    for href in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
        match = MAIN_RE.search(href)
        if not match:
            continue
        slug = match.group(1).lower()
        if slug in SKIP_MAIN_SLUGS:
            continue
        if any(
            key in slug
            for key in (
                "eten",
                "koken",
                "klussen",
                "sport",
                "wonen",
                "mode",
                "baby",
                "assortiment",
                "huishouden",
                "tuin",
                "sale",
            )
        ):
            seeds.append(f"https://www.lidl.nl/c/{slug}/{match.group(2)}")

    seeds = list(dict.fromkeys(seeds))
    print(f"🏬 Visiting {len(seeds)} main departments for leaf discovery")

    for seed in seeds:
        print(f"🔎 Discovering Lidl leaves from {seed}")
        try:
            goto_resilient(page, seed)
            page.wait_for_timeout(1500)
            accept_common_cookies(page)
        except Exception as err:
            print(f"⚠️ Skipping main {seed}: {err}")
            continue

        html = page.content()
        for match in LEAF_RE.finditer(html):
            slug, cat_id = match.group(1).lower(), match.group(2)
            found[cat_id] = f"https://www.lidl.nl/h/{slug}/{cat_id}"

        for href in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
            canonical = _canonical_leaf_url(href)
            if not canonical:
                continue
            found[canonical.rsplit("/", 1)[-1]] = canonical

    urls = sorted(found.values())
    if urls:
        print(f"✅ Discovered {len(urls)} leaf categories across Lidl menu")
        return urls

    print("⚠️ Leaf discovery empty; using fallback leaf list")
    return list(FALLBACK_LEAF_URLS)


def _product_from_grid(data: dict, category: str) -> dict | None:
    title = (data.get("fullTitle") or data.get("title") or "").strip()
    if not title:
        return None

    price_obj = data.get("price") if isinstance(data.get("price"), dict) else {}
    price = price_obj.get("price")
    if price is None:
        return None

    image = None
    image_v1 = data.get("image_V1")
    if isinstance(image_v1, dict):
        image = image_v1.get("image")
    image = image or data.get("image")

    barcode = None
    ians = data.get("ians")
    if isinstance(ians, list) and ians:
        first = ians[0]
        if isinstance(first, dict):
            barcode = first.get("ian") or first.get("gtin") or first.get("ean")
        elif isinstance(first, str):
            barcode = first

    return {
        "raw_text": f"{title}\n{price}",
        "image": image,
        "category": category,
        "barcode": barcode,
        "product_id": data.get("productId") or data.get("itemId") or data.get("erpNumber"),
    }


def _collect_page_products(page, category: str, seen: set[str]) -> list[dict]:
    items: list[dict] = []

    payloads = page.eval_on_selector_all(
        "[data-grid-data]",
        "els => els.map(e => e.getAttribute('data-grid-data')).filter(Boolean)",
    )
    if payloads:
        for raw in payloads:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            product = _product_from_grid(data, category)
            if not product:
                continue
            key = str(product.get("product_id") or product["raw_text"])
            if key in seen:
                continue
            seen.add(key)
            items.append(product)
        return items

    try:
        wait_for_products(page, "div.odsc-tile", timeout=10000)
    except Exception:
        return []

    cards = page.query_selector_all("div.odsc-tile")
    for card in cards:
        text = card.inner_text().strip()
        if not text or text in seen:
            continue
        seen.add(text)
        img = card.query_selector("img.odsc-image-gallery__image")
        src = img.get_attribute("src") if img else None
        items.append({"raw_text": text, "image": src, "category": category})
    return items


def scrape_lidl_category(page, url: str, seen: set[str]) -> list[dict]:
    """Scrape a category across all ?offset= pages (step 48)."""
    category = category_from_url(url) or (_leaf_slug(url) or "lidl")
    items: list[dict] = []
    base = _with_offset(url, 0)

    for offset in range(0, MAX_OFFSET + 1, OFFSET_STEP):
        page_url = _with_offset(base, offset)
        goto_resilient(page, page_url)
        page.wait_for_timeout(1200)
        if offset == 0:
            accept_common_cookies(page)

        page_items = _collect_page_products(page, category, seen)
        print(f"   offset={offset}: +{len(page_items)} new")
        if not page_items:
            if offset == 0:
                return []
            break
        items.extend(page_items)

    return items


def scrape_lidl_pages() -> None:
    all_data: list[dict] = []
    seen: set[str] = set()
    failures: list[tuple[str, str]] = []
    leaf_urls: list[str] = []

    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        configure_page(page)

        try:
            leaf_urls = discover_leaf_urls(page)
            # Prefer leaves; also hit seed mains once for any leftover tiles.
            urls = list(dict.fromkeys([*leaf_urls, *SEED_CATEGORY_URLS]))

            for url in urls:
                print(f"🌐 Scraping: {url}")
                try:
                    before = len(all_data)
                    items = scrape_lidl_category(page, url, seen)
                    if not items:
                        print(f"⚠️ Empty Lidl category: {url}")
                        continue
                    if urlparse(url).path.startswith("/c/"):
                        print(f"📦 Main department added {len(items)} new items")
                    else:
                        require_products(len(items), url, min_count=0)
                    all_data.extend(items)
                    print(
                        f"✅ Scraped {len(items)} new items from this category. "
                        f"Total: {len(all_data)} (+{len(all_data) - before})"
                    )
                except Exception as err:
                    msg = f"{type(err).__name__}: {err}"
                    print(f"❌ Failed to scrape {url}: {msg}")
                    failures.append((url, msg))
        finally:
            context.close()
            browser.close()

    out = Path("lidl.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(all_data, handle, indent=2, ensure_ascii=False)
    print(f"✅ Scraped {len(all_data)} items total.")
    print(f"✅ Done! Saved to '{out}'")

    report_batch_failures(failures, max(len(leaf_urls), 1), max_failure_ratio=0.5)


if __name__ == "__main__":
    scrape_lidl_pages()
