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

unit_pattern = re.compile(
    r"\b(per\s*)?\d+\s?(g|kg|ml|l|cl|stuks?|x\s?\d+.*|st|gram)\b", re.IGNORECASE
)
price_pattern = re.compile(r"\d+[.,]?\d{2}")

offer_keywords = [
    "nu voor",
    "2 VOOR",
    "3 VOOR",
    "4 VOOR",
    "6 VOOR",
    "aanbieding",
    "gratis",
    "3+1 GRATIS",
    "1+1 GRATIS",
    "GRATIS BEZORGING",
    "25 % KORTING",
    "15 % KORTING",
    "50 % KORTING",
    "1+2 GRATIS",
    "2+1 GRATIS",
    "1.00 KORTING",
    "2E 50% KORTING",
    "OP=OP",
    "2E HALVE PRIJS",
    "500 GRAM 4.99",
    "250 GRAM 2.69",
]


def extract_price(lines):
    joined = " ".join(lines)
    collapsed = re.sub(r"[\s\n]+", "", joined).replace(",", ".")

    matches = re.findall(r"\d+\.\d{2}", collapsed)
    if not matches:
        fallback = re.findall(r"\b\d{3}\b", collapsed)
        if fallback:
            try:
                prices = [float(f"{p[:-2]}.{p[-2:]}") for p in fallback]
                return f"{min(prices):.2f}"
            except ValueError:
                return ""
    else:
        try:
            prices = [float(p) for p in matches]
            return f"{min(prices):.2f}"
        except ValueError:
            return ""
    return ""


def extract_size(lines):
    for line in lines:
        match = unit_pattern.search(line)
        if match:
            return match.group()
    return ""


def clean_name(name):
    # Remove size patterns from name
    cleaned = re.sub(unit_pattern, "", name).strip()
    # Remove extra whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def has_offer_keywords(text):
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in offer_keywords)


def parse_entry(entry):
    raw_lines = [line.strip() for line in entry["raw_text"].split("\n") if line.strip()]

    is_offer = raw_lines and has_offer_keywords(raw_lines[0])

    if is_offer:
        # Find where offer lines end and product name begins
        offer_lines = []
        name_index = 0

        for i, line in enumerate(raw_lines):
            if has_offer_keywords(line):
                offer_lines.append(line)
                name_index = i + 1
            else:
                break

        offer = " ".join(offer_lines)
        name = clean_name(raw_lines[name_index]) if name_index < len(raw_lines) else ""

        # Size is typically the next line after name
        size_index = name_index + 1
        size = ""
        if size_index < len(raw_lines):
            size_line = raw_lines[size_index]
            match = unit_pattern.search(size_line)
            if match:
                size = match.group()
    else:
        name = clean_name(raw_lines[0]) if raw_lines else ""
        offer = ""
        size = extract_size(raw_lines)

    price = extract_price(raw_lines)
    image = entry.get("image", "")

    return structured_with_category(
        entry,
        {"n": name, "o": offer, "s": size, "p": price, "l": image},
    )


def main():
    input_file = "plus.json"
    output_file = "structured_plus.json"

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        structured = [parse_entry(entry) for entry in data]

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(structured, f, indent=2, ensure_ascii=False)

        print(f"✅ Processed {len(data)} entries")
        print(f"✅ Output saved to '{output_file}'")

    except Exception as e:
        print(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    main()
