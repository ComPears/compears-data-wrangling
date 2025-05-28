import json
import re
import os
import glob
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

# Configuration
OFFER_KEYWORDS = [
    "korting",
    "actie",
    "van ",
    "voor ",
    "deal",
    "2 voor",
    "aanbieding",
    "probeer prijs",
]
UNIT_PATTERN = re.compile(r"\b\d+([.,]?\d+)?\s?(g|kg|ml|l|cl|stuks?|x\s?\d+.*)\b", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"\d+[.,]\d{2}")

def get_filename_from_url(url):
    """Extract a filename from a URL."""
    path = urlparse(url).path
    last_part = path.rstrip("/").split("/")[-1]
    return last_part or "unknown"

def scrape_jumbo_products(link_list):
    """Scrape product data from Jumbo website using Playwright."""
    os.makedirs("JSONs", exist_ok=True)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1600, "height": 900})
        page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
            }
        )

        for link in link_list:
            filename_suffix = get_filename_from_url(link)
            print(f"\n🔄 Scraping: {link}")
            page.goto(link, wait_until="load", timeout=60000)
            page.wait_for_timeout(3000)

            try:
                print("🍪 Trying to accept cookie consent...")
                consent_button = page.locator("button:has-text('Akkoord')")
                if consent_button.is_visible():
                    consent_button.click()
                    print("✅ Cookie banner closed.")
                    page.wait_for_timeout(2000)
            except Exception as e:
                print(f"⚠️ Cookie banner not handled: {e}")

            seen = set()
            data = []
            click_count = 0

            while True:
                cards = page.query_selector_all("article.product-container")
                print(f"🔍 Found {len(cards)} product cards on this page")

                new_items = 0
                for card in cards:
                    raw_text = card.inner_text().strip()
                    if raw_text in seen:
                        continue
                    seen.add(raw_text)

                    img = card.query_selector(
                        'div.product-image img[data-testid="jum-product-image"]'
                    )
                    src = img.get_attribute("src") if img else None

                    data.append({"raw_text": raw_text, "image": src})
                    new_items += 1

                try:
                    more_btn = page.locator("button:has-text('Volgende')")
                    if more_btn.is_visible() and more_btn.is_enabled():
                        print(f"➕ Click #{click_count + 1} on 'Volgende'")
                        more_btn.scroll_into_view_if_needed()
                        more_btn.click()
                        page.wait_for_timeout(3000)
                        click_count += 1
                    else:
                        print("✅ No more 'Volgende' button or it's disabled.")
                        break
                except Exception as e:
                    print(f"⚠️ Error during 'Volgende' click: {e}")
                    break

            print(f"✅ Total unique products: {len(data)}")
            output_file = f"JSONs/jumbo_products_{filename_suffix}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        browser.close()

def merge_json_files(folder_path, output_file):
    """Merge all JSON files in a folder into a single JSON file."""
    if not os.path.exists(folder_path):
        print(f"Error: The folder '{folder_path}' does not exist.")
        return

    merged_data = []
    json_files = glob.glob(os.path.join(folder_path, "*.json"))

    if not json_files:
        print(f"No JSON files found in '{folder_path}'.")
        return

    print(f"Found {len(json_files)} JSON files to merge.")

    for file_path in json_files:
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    merged_data.extend(data)
                elif isinstance(data, dict):
                    merged_data.append(data)
                print(f"Processed: {os.path.basename(file_path)}")
        except json.JSONDecodeError:
            print(f"Error: Could not parse '{file_path}' as JSON. Skipping.")
        except Exception as e:
            print(f"Error processing '{file_path}': {str(e)}")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, indent=4, ensure_ascii=False)

    print(f"Successfully merged {len(json_files)} JSON files into '{output_file}'.")

def parse_entry(entry):
    """Parse a single product entry into structured data."""
    raw_lines = [line.strip() for line in entry["raw_text"].split("\n") if line.strip()]

    # 1. Name: first non-empty line
    name = raw_lines[0] if raw_lines else ""
    namelen = len(name) - 5
    only_name = name[0:namelen]

    # 2. Offer: only lines with clear keywords
    offer_lines = [
        line for line in raw_lines if any(k in line.lower() for k in OFFER_KEYWORDS)
    ]
    offer = " ".join(offer_lines) if offer_lines else ""

    # 3. Price: pick the lowest float value found
    all_prices = re.findall(PRICE_PATTERN, entry["raw_text"])
    price = (
        f"{min([float(p.replace(',', '.')) for p in all_prices]):.2f}"
        if all_prices
        else ""
    )

    # 4. Size: match size units like "400 g", "1 kg", "6 x 250ml", etc.
    size = ""
    for line in raw_lines:
        match = UNIT_PATTERN.search(line)
        if match:
            size = match.group()
            break

    # 5. Image link
    image = entry.get("image", "")

    return {"n": only_name, "p": price, "o": offer, "s": size, "l": image}

def structure_data(input_file, output_file):
    """Structure the raw scraped data into a more organized format."""
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    structured = [parse_entry(entry) for entry in data]

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False)

    print(f"✅ Done! Structured output saved to '{output_file}'")

def main(links):
    """Main function to execute all steps in sequence."""
    # Step 1: Scrape data
    print("\n=== STEP 1: SCRAPING PRODUCT DATA ===")
    scrape_jumbo_products(links)
    
    # Step 2: Merge JSON files
    print("\n=== STEP 2: MERGING JSON FILES ===")
    merge_json_files("JSONs", "Jumbo.json")
    
    # Step 3: Structure the data
    print("\n=== STEP 3: STRUCTURING DATA ===")
    structure_data("Jumbo.json", "jumbo_structured.json")
    
    print("\n✅ All steps completed successfully!")

if __name__ == "__main__":
    # Import your links or define them here
    from links import links  # Your list of product URLs
    
    main(links)