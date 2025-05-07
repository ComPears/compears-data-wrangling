import json
import re
import os

# Folder where your files are stored (change if needed)
input_folder = "./raw_with_image_links"
output_folder = "structured_with_links"

# Keywords and patterns
offer_keywords = ["gratis", "voor", "vanaf", "%", "1+1", "2e"]
unit_pattern = re.compile(r"per\s\w+|\d+\s?(ml|g|kg|l|stuk|stuks|cl|meter|m)", re.IGNORECASE)

# Function to parse product entry
def parse_product(entry):
    raw = entry.get("raw_text", "")
    image_link = entry.get("image", "")
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    name = lines[0] if lines else ""

    offer = next((line for line in lines if any(k in line.lower() for k in offer_keywords)), "")
    price_match = next((line for line in lines if re.match(r"^\d+[\.,]?\d*$", line)), "")
    price = price_match.replace(",", ".") if price_match else ""
    unit_lines = [line for line in lines if unit_pattern.search(line.lower())]
    unit = unit_lines[-1] if unit_lines else ""

    return {
        "n": name,
        "o": offer,
        "p": price,
        "s": unit,
        "l": image_link
    }

# Loop through all .json files
for file in os.listdir(input_folder):
    if file.endswith(".json"):
        input_path = os.path.join(input_folder, file)
        output_path = os.path.join(output_folder, f"structured_{file}")

        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            structured = [parse_product(entry) for entry in data]

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(structured, f, indent=2, ensure_ascii=False)

            print(f"✅ {file} → {output_path}")
        except Exception as e:
            print(f"❌ Failed to process {file}: {e}")
