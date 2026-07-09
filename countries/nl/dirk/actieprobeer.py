import json
import re
import sys
from pathlib import Path

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
from category_utils import structured_with_category

# Load the input file
with open("JSONs/dirk_probeer_prijs_actie.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Keywords and patterns

# put "probeer prijs" here
offer_keywords = ["actie", "van", "1+1", "2e", "%", "gratis", "vanaf"]
unit_pattern = re.compile(
    r"^\d+([.,]?\d+)?\s?(g|kg|ml|l|liter|cl|stuks?|x.*)$", re.IGNORECASE
)
price_pattern = re.compile(r"^\d+$")


def parse_entry(entry):
    raw_lines = [line.strip() for line in entry["raw_text"].split("\n") if line.strip()]
    image_links = entry["image"]
    name, offer_lines, price_parts, size = "", [], [], ""

    # Offer lines
    for i in range(len(raw_lines)):
        if any(k in raw_lines[i].lower() for k in offer_keywords):
            offer_lines.append(raw_lines[i])
    raw_lines = [line for line in raw_lines if line not in offer_lines]
    offer = " ".join(offer_lines)

    # Price
    while raw_lines and price_pattern.fullmatch(raw_lines[0]):
        price_parts.append(raw_lines.pop(0))

    if len(price_parts) == 2:
        price = ".".join(price_parts)
    elif len(price_parts) == 1:
        price = f"0.{price_parts[0]}"
    else:
        price = ""

    # Size
    for i, line in enumerate(raw_lines):
        if unit_pattern.fullmatch(line):
            size = line
            raw_lines.pop(i)
            break

    # Name
    name = " ".join(raw_lines).strip()

    return structured_with_category(
        entry,
        {"n": name, "p": price, "o": offer, "s": size, "l": image_links},
    )


# Parse all entries
structured = [parse_entry(entry) for entry in data]

# Save output
with open("JSONs/dirk_actie_probeer_structured.json", "w", encoding="utf-8") as f:
    json.dump(structured, f, indent=2, ensure_ascii=False)

print("✅ Done! Saved to 'dirk_actie_probeer_structured.json'")
