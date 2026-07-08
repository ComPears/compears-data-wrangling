import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from category_utils import structured_with_category

# Load the raw scraped file
with open("Jumbo.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Keyword and regex patterns

offer_keywords = [
    "nu voor",
    "korting",
    "actie",
    "deal",
    "2 voor",
    "3 voor",
    "aanbieding",
    "probeer prijs",
    "2 + 1 GRATIS",
    "1 + 1 GRATIS",
    "2 VOOR",
    "3 VOOR",
    "4 VOOR",
    "6 VOOR",
    "2 voor 6.00",
    "aanbieding",
    "gratis",
    "3+1 GRATIS",
    "1+1 GRATIS",
    "GRATIS BEZORGING",
    "25 % KORTING",
    "15 % KORTING",
    "50 % KORTING",
    "1.00 KORTING",
    "2E 50% KORTING",
    "OP=OP",
    "2E HALVE PRIJS",
]

unit_pattern = re.compile(
    r"\b\d+([.,]?\d+)?\s?(g|kg|ml|l|cl|stuks?|x\s?\d+.*)\b", re.IGNORECASE
)
price_pattern = re.compile(r"\d+[.,]\d{2}")


def parse_entry(entry):
    raw_lines = [line.strip() for line in entry["raw_text"].split("\n") if line.strip()]

    # 1. Name: first non-empty line
    name = raw_lines[0] if raw_lines else ""
    namelen= len(name) - 5
    only_name = name[0:namelen]

    # 2. Offer: only lines with clear keywords
    offer_lines = [
        line
        for line in raw_lines
        if any(
            re.search(rf"\b{re.escape(k.lower())}\b", line.lower())
            for k in offer_keywords
        )
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

    return structured_with_category(
        entry,
        {"n": only_name, "p": price, "o": offer, "s": size, "l": image},
    )


# # Apply to all entries
structured = [parse_entry(entry) for entry in data]


# Save to file
with open("jumbo_structured.json", "w", encoding="utf-8") as f:
    json.dump(structured, f, indent=2, ensure_ascii=False)

print("✅ Done! Structured output saved to 'jumbo_structured.json'")
