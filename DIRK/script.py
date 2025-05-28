import json
import os
import re
from playwright.sync_api import sync_playwright
from playwright._impl._errors import TimeoutError

# Configuration
INPUT_LINKS_MODULE = "links2"  # Module containing the links to scrape
OUTPUT_DIR = "JSONs"
RAW_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "dirk.json")
ACTIE_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "dirk_probeer_prijs_actie.json")
STRUCTURED_FILE = os.path.join(OUTPUT_DIR, "dirk_structured.json")
ACTIE_STRUCTURED_FILE = os.path.join(OUTPUT_DIR, "dirk_actie_probeer_structured.json")
FINAL_FILE = os.path.join(OUTPUT_DIR, "final.json")
FINAL_OUTPUT_FILE = "dirk_all.json"

# Keywords and patterns for processing
OFFER_KEYWORDS = ["actie", "1+1", "2e", "%", "gratis", "vanaf", "probeer prijs"]
UNIT_PATTERN = re.compile(r"^\s*\d+([.,]?\d+)?\s?(g|kg|ml|l|liter|cl|stuks?|x)\s*$", re.IGNORECASE)
DIGIT_LINE = re.compile(r"^\d+$")
PRICE_PATTERN = re.compile(r"^\d+$")

def scrape_products():
    """Scrape product data from the website and save to JSON file."""
    try:
        from links2 import links
    except ImportError:
        print("❌ Error: Could not import 'links' from links2.py")
        return

    # Load existing data if file exists
    if os.path.exists(RAW_OUTPUT_FILE):
        with open(RAW_OUTPUT_FILE, "r", encoding="utf-8") as f:
            product_data = json.load(f)
    else:
        product_data = []

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        print("🔄 Opening AH.nl...")
        page.set_viewport_size({"width": 390, "height": 844})
        page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
            }
        )

        for url in links:
            print(f"🌐 Scraping: {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
            except TimeoutError:
                print(f"⚠️ Timeout on {url}, trying domcontentloaded instead...")
                page.goto(url, wait_until="domcontentloaded")

            page.wait_for_timeout(2000)
            print("🔄 Loading all products...")

            try:
                cards = page.query_selector_all("article[data-product-id]")
                new_data = []

                for card in cards:
                    raw_text = card.inner_text().strip()
                    img_el = card.query_selector("img.main-image")
                    img_src = img_el.get_attribute("src") if img_el else None
                    new_data.append({"raw_text": raw_text, "image": img_src})

                product_data.extend(new_data)

                # Save progress after every page
                with open(RAW_OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(product_data, f, indent=2, ensure_ascii=False)

                print(f"✅ Scraped {len(cards)} products from this page. Total saved: {len(product_data)}")

            except Exception as e:
                print(f"❌ Error scraping {url}: {e}")
                continue

        print(f"🏁 All done! {len(product_data)} total products saved.")
        browser.close()

def split_special_offers():
    """Split items with special offers into a separate file."""
    if not os.path.exists(RAW_OUTPUT_FILE):
        return print(f"❌ File not found: {RAW_OUTPUT_FILE}")

    try:
        with open(RAW_OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return print("⚠️ Expected a list of items in the JSON file.")

        matched_items = []
        remaining_items = []

        for item in data:
            raw_text = item.get("raw_text", "")
            if any(keyword.lower() in raw_text.lower() for keyword in OFFER_KEYWORDS):
                matched_items.append(item)
            else:
                remaining_items.append(item)

        # Save matched items to a separate file
        with open(ACTIE_OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(matched_items, f, indent=2, ensure_ascii=False)

        # Overwrite original file with remaining items
        with open(RAW_OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(remaining_items, f, indent=2, ensure_ascii=False)

        print(f"✅ Moved {len(matched_items)} items containing special offers to: {ACTIE_OUTPUT_FILE}")
        print(f"✅ Remaining {len(remaining_items)} items saved to: {RAW_OUTPUT_FILE}")

    except Exception as e:
        print(f"⚠️ Error processing file: {e}")

def parse_regular_entries():
    """Parse the regular entries (non-special offers)."""
    if not os.path.exists(RAW_OUTPUT_FILE):
        return print(f"❌ File not found: {RAW_OUTPUT_FILE}")

    with open(RAW_OUTPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    cleaned_data = [parse_entry(entry) for entry in data]

    with open(STRUCTURED_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Restructured regular data saved to: {STRUCTURED_FILE}")

def parse_special_offer_entries():
    """Parse the special offer entries."""
    if not os.path.exists(ACTIE_OUTPUT_FILE):
        return print(f"❌ File not found: {ACTIE_OUTPUT_FILE}")

    with open(ACTIE_OUTPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    structured = [parse_special_offer_entry(entry) for entry in data]

    with open(ACTIE_STRUCTURED_FILE, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False)

    print(f"✅ Restructured special offer data saved to: {ACTIE_STRUCTURED_FILE}")

def parse_entry(entry):
    """Parse a regular product entry."""
    lines = [line.strip() for line in entry["raw_text"].splitlines() if line.strip()]
    image_links = entry["image"]
    price_parts = []

    # Step 1: Extract price block
    while lines and DIGIT_LINE.fullmatch(lines[0]):
        price_parts.append(lines.pop(0))
    price = ".".join(price_parts) if price_parts else ""

    # Step 2: Remaining lines could include name, size, offer
    name_lines = []
    size = ""
    offer = ""

    for line in lines:
        if not size and UNIT_PATTERN.fullmatch(line):
            size = line
        elif not offer and any(k in line.lower() for k in OFFER_KEYWORDS):
            offer = line
        else:
            name_lines.append(line)

    name = " ".join(name_lines)

    return {"n": name, "p": price, "o": offer, "s": size, "l": image_links}

def parse_special_offer_entry(entry):
    """Parse a special offer product entry."""
    raw_lines = [line.strip() for line in entry["raw_text"].split("\n") if line.strip()]
    image_links = entry["image"]
    name, offer_lines, price_parts, size = "", [], [], ""

    # Offer lines
    for i in range(len(raw_lines)):
        if any(k in raw_lines[i].lower() for k in OFFER_KEYWORDS):
            offer_lines.append(raw_lines[i])
    raw_lines = [line for line in raw_lines if line not in offer_lines]
    offer = " ".join(offer_lines)

    # Price
    while raw_lines and PRICE_PATTERN.fullmatch(raw_lines[0]):
        price_parts.append(raw_lines.pop(0))

    if len(price_parts) == 2:
        price = ".".join(price_parts)
    elif len(price_parts) == 1:
        price = f"0.{price_parts[0]}"
    else:
        price = ""

    # Size
    for i, line in enumerate(raw_lines):
        if UNIT_PATTERN.fullmatch(line):
            size = line
            raw_lines.pop(i)
            break

    # Name
    name = " ".join(raw_lines).strip()

    return {"n": name, "p": price, "o": offer, "s": size, "l": image_links}

def merge_structured_data():
    """Merge regular and special offer structured data."""
    if not os.path.exists(STRUCTURED_FILE):
        return print(f"❌ File not found: {STRUCTURED_FILE}")
    if not os.path.exists(ACTIE_STRUCTURED_FILE):
        return print(f"❌ File not found: {ACTIE_STRUCTURED_FILE}")

    with open(STRUCTURED_FILE, "r", encoding="utf-8") as f1:
        data1 = json.load(f1)

    with open(ACTIE_STRUCTURED_FILE, "r", encoding="utf-8") as f2:
        data2 = json.load(f2)

    data3 = data1 + data2

    with open(FINAL_FILE, "w", encoding="utf-8") as f3:
        json.dump(data3, f3, ensure_ascii=False, indent=2)

    print(f"✅ Merged data saved to: {FINAL_FILE}")

def fix_decimal_prices():
    """Convert whole number prices to decimal format."""
    if not os.path.exists(FINAL_FILE):
        return print(f"❌ File not found: {FINAL_FILE}")

    with open(FINAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        price = item.get("p")
        if price and price.isdigit():  # whole number string like "85"
            item["p"] = f"0.{price.zfill(2)}"  # Ensure 2-digit format

    with open(FINAL_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Final output with decimal prices saved to: {FINAL_OUTPUT_FILE}")

def main():
    """Main workflow execution."""
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Execute all steps in order
    scrape_products()
    split_special_offers()
    parse_regular_entries()
    parse_special_offer_entries()
    merge_structured_data()
    fix_decimal_prices()

    print("🏁 All processing complete!")

if __name__ == "__main__":
    main()