import json
import os
import re
import glob
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from links import links  # Your list of product URLs

def get_filename_from_url(url):
    """Extracts a filename from a URL path."""
    path = urlparse(url).path
    # Remove trailing slash if present and take the last segment
    last_part = path.rstrip("/").split("/")[-1]
    return last_part or "unknown"

def scrape_jumbo_products(link_list):
    """Scrapes product data from Jumbo website URLs."""
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
    """
    Merges all JSON files in the specified folder into a single JSON file.
    
    Args:
        folder_path: Path to the folder containing JSON files
        output_file: Name of the output merged JSON file
    """
    # Make sure the folder path exists
    if not os.path.exists(folder_path):
        print(f"Error: The folder '{folder_path}' does not exist.")
        return None

    # Initialize an empty list to store all the data
    merged_data = []

    # Get all JSON files in the folder
    json_files = glob.glob(os.path.join(folder_path, "*.json"))

    # Check if any JSON files were found
    if not json_files:
        print(f"No JSON files found in '{folder_path}'.")
        return None

    print(f"Found {len(json_files)} JSON files to merge.")

    # Process each JSON file
    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                # Load JSON data
                data = json.load(f)

                # If the data is a list, extend the merged_data list
                if isinstance(data, list):
                    merged_data.extend(data)
                # If the data is a dictionary, append it to the merged_data list
                elif isinstance(data, dict):
                    merged_data.append(data)

                print(f"Processed: {os.path.basename(file_path)}")

        except json.JSONDecodeError:
            print(f"Error: Could not parse '{file_path}' as JSON. Skipping.")
        except Exception as e:
            print(f"Error processing '{file_path}': {str(e)}")

    # Write the merged data to the output file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, indent=4, ensure_ascii=False)

    print(f"Successfully merged {len(json_files)} JSON files into '{output_file}'.")
    return merged_data

def structure_data(input_file, output_file):
    """Structures raw product data into a consistent format."""
    # Keyword and regex patterns
    offer_keywords = [
        "korting",
        "actie",
        "van ",
        "voor ",
        "deal",
        "2 voor",
        "aanbieding",
        "probeer prijs",
    ]
    unit_pattern = re.compile(
        r"\b\d+([.,]?\d+)?\s?(g|kg|ml|l|cl|stuks?|x\s?\d+.*)\b", re.IGNORECASE
    )
    price_pattern = re.compile(r"\d+[.,]\d{2}")

    def parse_entry(entry):
        raw_lines = [line.strip() for line in entry["raw_text"].split("\n") if line.strip()]

        # 1. Name: first non-empty line
        name = raw_lines[0] if raw_lines else ""
        namelen = len(name) - 5
        only_name = name[0:namelen]

        # 2. Offer: only lines with clear keywords
        offer_lines = [
            line for line in raw_lines if any(k in line.lower() for k in offer_keywords)
        ]
        offer = " ".join(offer_lines) if offer_lines else ""

        # 3. Price: pick the lowest float value found
        all_prices = re.findall(price_pattern, entry["raw_text"])
        price = (
            f"{min([float(p.replace(',', '.')) for p in all_prices]):.2f}"
            if all_prices
            else ""
        )

        # 4. Size: match size units like "400 g", "1 kg", "6 x 250ml", etc.
        size = ""
        for line in raw_lines:
            match = unit_pattern.search(line)
            if match:
                size = match.group()
                break

        # 5. Image link
        image = entry.get("image", "")

        return {"n": only_name, "p": price, "o": offer, "s": size, "l": image}

    # Load the raw scraped file
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Apply to all entries
    structured = [parse_entry(entry) for entry in data]

    # Save to file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False)

    print(f"✅ Done! Structured output saved to '{output_file}'")
    return structured

def clean_data(input_file, key="n"):
    """Removes duplicate items from JSON data based on a specified key."""
    # Load JSON data from file
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Initial items in list: {len(data)}")

    seen = set()
    cleaned_data = []

    for item in data:
        name = item.get(key, "").strip()

        # Skip items with empty or missing name
        if not name:
            continue

        # Skip duplicates
        if name not in seen:
            seen.add(name)
            cleaned_data.append(item)

    print(
        f"Total duplicates removed: {len(data) - len(cleaned_data)}, Total items: {len(data)}, Final items: {len(cleaned_data)}"
    )
    print(f"Final items in list: {len(cleaned_data)}")

    # Save cleaned data to output JSON
    with open(input_file, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, indent=2, ensure_ascii=False)

    return cleaned_data

def main():
    # Step 1: Scrape the data from all URLs
    scrape_jumbo_products(links)
    
    # Step 2: Merge all scraped JSON files into one
    merged_output = "Jumbo.json"
    merge_json_files("JSONs", merged_output)
    
    # Step 3: Structure the raw data
    structured_output = "jumbo_structured.json"
    structure_data(merged_output, structured_output)
    
    # Step 4: Clean the structured data
    clean_data(structured_output)
    
    print("✅ All processing steps completed successfully!")

if __name__ == "__main__":
    main()