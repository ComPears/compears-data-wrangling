import json
import re
import os
from playwright.sync_api import sync_playwright
from links_dictionary import get_ah_links

# Configuration
input_folder = "./new_results"
output_file = "structured_all_merged.json"

# Patterns for parsing
unit_pattern = re.compile(
    r"per\s\w+|\d+\s?(ml|g|kg|l|stuk|stuks|cl|meter|m)", re.IGNORECASE
)
offer_keywords = ["gratis", "voor", "vanaf", "%", "1+1", "2e"]

# Patterns to remove from raw_text
DEFAULT_PATTERNS_TO_REMOVE = [
    "AH "
]

def scrape_ah_products(links, output_file):
    if isinstance(links, str):
        links = [links]  # wrap single link in list

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        all_products = []

        for url in links:
            print(f"🔄 Opening {url}...")
            page.set_viewport_size({"width": 390, "height": 844})
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
            })
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(3000)

            # 🍪 Accept cookies
            try:
                accept_btn = page.query_selector("button:has-text('Accepteren')")
                if accept_btn:
                    accept_btn.click()
                    print("clicked accept button")
                    page.wait_for_timeout(1000)
            except Exception as e:
                print("⚠️ Error clicking cookie button:", e)

            # 🔄 Click 'More results' until gone
            print("🔄 Loading all products...")
            print("🔄 Loading all products via 'More results' button...")

            click_count = 0
            while True:
                try:
                    more_btn = page.query_selector('button[data-testhook="load-more"]')
                    
                    if more_btn and more_btn.is_enabled():
                        print(f"➕ Click #{click_count + 1} on 'More results'")
                        more_btn.click()
                        page.wait_for_timeout(2000)

                        # Scroll to bottom to force product load
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1500)

                        click_count += 1
                    else:
                        print("✅ 'More results' button not found or disabled.")
                        break
                except Exception as e:
                    print("⚠️ Error during load-more clicking:", e)
                    break

            # 🧊 Scrape and structure product info
            cards = page.query_selector_all("article[data-testhook='product-card']")
            print(f"🔍 Found {len(cards)} products.")

            for card in cards:
                raw_text = card.inner_text().strip()
                img_card = card.query_selector("img[data-testhook='product-image']")
                img_src = img_card.get_attribute("src") if img_card else None
                all_products.append({
                    "raw_text": raw_text,
                    "image": img_src
                })

        # Ensure the output directory exists
        os.makedirs(input_folder, exist_ok=True)
        filename = f"{input_folder}/{output_file}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(all_products, f, indent=2, ensure_ascii=False)

        print(f"✅ Done! {len(all_products)} products saved to {output_file}")
        browser.close()

def clean_raw_text_in_file(file_path, patterns_to_remove=None):
    if patterns_to_remove is None:
        patterns_to_remove = DEFAULT_PATTERNS_TO_REMOVE
        
    if not os.path.exists(file_path):
        return print(f"❌ File not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data if isinstance(data, list) else []:
            if "raw_text" in item:
                for pattern in patterns_to_remove:
                    if pattern in item["raw_text"]:
                        item["raw_text"] = item["raw_text"].replace(pattern, "")

        base, ext = os.path.splitext(file_path)
        output_file = f"{base}{ext}"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✅ Cleaned file saved to: {output_file}")

    except Exception as e:
        print(f"⚠️ Error processing file: {e}")

def parse_product(entry):
    raw = entry.get("raw_text", "")
    image_link = entry.get("image", "")
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    name = lines[0] if lines else ""

    offer = next(
        (line for line in lines if any(k in line.lower() for k in offer_keywords)), ""
    )
    price_match = next(
        (
            re.search(r"(\d+[.,]?\d*)", line)
            for line in lines
            if re.search(r"(\d+[.,]?\d*)", line)
        ),
        None,
    )
    price = price_match.group(1).replace(",", ".") if price_match else ""
    unit_lines = [line for line in lines if unit_pattern.search(line.lower())]
    unit = unit_lines[-1] if unit_lines else ""

    return {"n": name, "o": offer, "p": price, "s": unit, "l": image_link}

def parse_all_json_files():
    # List to hold all structured entries
    all_structured_data = []

    # Process each file and collect data
    for file in os.listdir(input_folder):
        if file.endswith(".json"):
            input_path = os.path.join(input_folder, file)
            try:
                with open(input_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                structured = [parse_product(entry) for entry in data]
                all_structured_data.extend(structured)
                print(f"✅ {file} processed.")
            except Exception as e:
                print(f"❌ Failed to process {file}: {e}")

    # Write the merged result to a single output file
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_structured_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ All data merged into: {output_file}")
    except Exception as e:
        print(f"\n❌ Failed to write merged file: {e}")

def main():
    # First scrape all products
    ah_links = get_ah_links()
    for name, url in ah_links.items():
        print(f"Scraping category: {name}")
        scrape_ah_products(url, name)
        # Clean each file right after scraping
        file_path = f"{input_folder}/{name}.json"
        clean_raw_text_in_file(file_path)
    
    # Then parse all the scraped data
    parse_all_json_files()

if __name__ == "__main__":
    main()