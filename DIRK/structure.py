import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from category_utils import structured_with_category

# Load original file
with open("JSONs/dirk.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Offer-related keywords and unit regex
offer_keywords = ["actie", "1+1", "2e", "%", "gratis", "vanaf"]
unit_pattern = re.compile(
    r"^\s*\d+([.,]?\d+)?\s?(g|kg|ml|l|liter|cl|stuks?|x)\s*$", re.IGNORECASE
)
digit_line = re.compile(r"^\d+$")


def parse_entry(entry):
    lines = [line.strip() for line in entry["raw_text"].splitlines() if line.strip()]
    image_links = entry["image"]
    price_parts = []

    # Step 1: Extract price block (e.g. "1", "99" → "1.99")
    while lines and digit_line.fullmatch(lines[0]):
        price_parts.append(lines.pop(0))
    price = ".".join(price_parts) if price_parts else ""

    # Step 2: Remaining lines could include name, size, offer
    name_lines = []
    size = ""
    offer = ""

    for line in lines:
        if not size and unit_pattern.fullmatch(line):
            size = line
        elif not offer and any(k in line.lower() for k in offer_keywords):
            offer = line
        else:
            name_lines.append(line)

    name = " ".join(name_lines)

    return structured_with_category(
        entry,
        {"n": name, "p": price, "o": offer, "s": size, "l": image_links},
    )


# Transform all entriesa
cleaned_data = [parse_entry(entry) for entry in data]

# Optionally write to file
with open("JSONs/dirk_structured.json", "w", encoding="utf-8") as f:
    json.dump(cleaned_data, f, indent=2, ensure_ascii=False)

print("✅ Restructured data is ready.")
