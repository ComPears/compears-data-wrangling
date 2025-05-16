import json
import re
import os

# Folder where your files are stored (change if needed)
input_folder = "./raw_with_image_links"
output_file = "structured_all_merged.json"

# Ensure unit detection is flexible
unit_pattern = re.compile(
    r"per\s\w+|\d+\s?(ml|g|kg|l|stuk|stuks|cl|meter|m)", re.IGNORECASE
)
offer_keywords = ["gratis", "voor", "vanaf", "%", "1+1", "2e"]


# Function to parse each product entry
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
