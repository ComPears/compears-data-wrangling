import json
import os
import glob
import re
from links import get_aldi_links,add_remaining_links
from playwright.sync_api import sync_playwright

# Step 1: Scraping (original main.py)
def scrape_aldi_products(link_dict):
    os.makedirs("aldi_results", exist_ok=True)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1600, "height": 900})
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
        })

        for name, url in link_dict.items():
            print(f"🔄 Scraping: {name} → {url}")
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(3000)

            data, seen = [], set()

            while True:
                cards = page.query_selector_all("div.product-tile")
                for card in cards:
                    raw_text = card.inner_text().strip()
                    if raw_text in seen: continue
                    seen.add(raw_text)
                    img_el = card.query_selector("img.product-tile__image-section__picture")
                    img_src = img_el.get_attribute("src") if img_el else None
                    data.append({"raw_text": raw_text, "image": img_src})

                more_btn = page.locator("button:has-text('Meer tonen')")
                if more_btn.is_visible():
                    more_btn.scroll_into_view_if_needed()
                    more_btn.click()
                    page.wait_for_timeout(3000)
                else:
                    break

            filename = f"aldi_results/{name}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✅ {len(data)} items saved to {filename}")

        browser.close()

# Step 2: Merging (original mergejson.py)
def merge_json_files(folder_path, output_file):
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
        json.dump(merged_data, f, indent=4)

    print(f"Successfully merged {len(json_files)} JSON files into '{output_file}'.")

# Step 3: Cleaning (original remove_patterns.py)
def clean_raw_text_in_file(file_path, patterns_to_remove):
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

# Step 4: Restructuring (original restructure.py)
def extract_product_info(raw_text, image_url):
    lines = raw_text.split("\n")
    product = {"n": "", "p": "", "o": "", "s": "", "i": image_url}

    if len(lines) >= 3:
        product["n"] = f"{lines[0].strip()} {lines[2].strip()}"

    for i, line in enumerate(lines):
        if re.match(r"\d+\.\d+|\d+", line.strip()) and i > 0:
            product["p"] = line.strip()
            break

    for line in lines:
        if re.search(r"(kg|g|ml|l|stuks|tabs|doekjes|stuk)", line, re.IGNORECASE):
            if not re.search(r"[a-z]+ = \d+\.\d+", line, re.IGNORECASE):
                product["s"] = line.strip()
                break

    for line in lines:
        if re.search(
            r"(aanbieding|korting|actie|sale|In de aanbieding vanaf \d+\.\d+)",
            line,
            re.IGNORECASE,
        ):
            product["o"] = line.strip()
            break

    return product

def extract_product_data(input_path, output_file):
    if not os.path.exists(input_path):
        print(f"Error: Path '{input_path}' does not exist.")
        return

    files = (
        [input_path]
        if input_path.endswith(".json")
        else glob.glob(os.path.join(input_path, "*.json"))
    )

    if not files:
        print(f"No JSON files found in '{input_path}'.")
        return

    all_products = []

    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                for item in data:
                    if "raw_text" in item and "image" in item:
                        all_products.append(
                            extract_product_info(item["raw_text"], item["image"])
                        )

            print(f"Processed: {os.path.basename(file)}")

        except Exception as e:
            print(f"Error processing '{file}': {e}")

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_products, f, indent=2, ensure_ascii=False)
        print(f"Output saved to {output_file}")
    except Exception as e:
        print(f"Error writing output file: {e}")

# Main execution
if __name__ == "__main__":
    # Configuration
    SCRAPING_FOLDER = "aldi_results"
    MERGED_FILE = "merged_aldi.json"
    FINAL_FILE = "structured_aldi.json"
    
    # Patterns to remove from raw text
    PATTERNS_TO_REMOVE = [
        "Barissimo\n\n",
        "Snack fan\n\n",
        "Potato king\n\n",
        "\nBoodschappenlijstje",
        "All seasons\n\n",
        "Barissimo\n\n",
        "Aldi\n\n"
    ]
    
    # Step 1: Scrape data (you'll need to provide the link_dict)
    print("\n=== STEP 1: Scraping ALDI products ===")
    scrape_aldi_products(add_remaining_links())
    
    # Step 2: Merge JSON files
    print("\n=== STEP 2: Merging JSON files ===")
    merge_json_files(SCRAPING_FOLDER, MERGED_FILE)
    
    # Step 3: Clean patterns from raw text
    print("\n=== STEP 3: Cleaning patterns from raw text ===")
    clean_raw_text_in_file(MERGED_FILE, PATTERNS_TO_REMOVE)
    
    # Step 4: Restructure data
    print("\n=== STEP 4: Restructuring data ===")
    extract_product_data(MERGED_FILE, FINAL_FILE)
    
    print("\n✅ All steps completed!")