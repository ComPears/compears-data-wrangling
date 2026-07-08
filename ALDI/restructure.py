import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from category_utils import structured_with_category


def parse_product_text(raw_text: str) -> dict:
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    info = {"name": "", "price": "", "size": "", "offer": ""}

    if not lines:
        return info

    # 1. Extract offer line
    promo_keywords = ["in de aanbieding", "actie", "korting", "op=op", "probeer prijs"]
    offer_line = ""
    for i, line in enumerate(lines):
        if any(line.lower().startswith(k) for k in promo_keywords):
            offer_line = line
            lines.pop(i)
            break
    info["offer"] = offer_line

    # 2. Extract price
    price_line = None
    for line in lines:
        if re.match(r"^\d+\.\d{2}$", line):
            info["price"] = line
            price_line = line
            break

    # 3. Extract size — normal patterns and "Inhoud: ..."
    size_keywords = [
        "g",
        "kg",
        "l",
        "ml",
        "cl",
        "stuks",
        "doekjes",
        "tabs",
        "porties",
        "plakjes",
        "kopjes",
    ]
    size = ""
    for line in lines:
        lower = line.lower()
        if line == price_line or "=" in line:
            continue

        # Handle "Inhoud: ..." lines
        if lower.startswith("inhoud:"):
            content = lower.replace("inhoud:", "").strip()
            size = content
            break

        # Handle typical size formats (with digits and keywords)
        if any(k in lower for k in size_keywords) and any(c.isdigit() for c in line):
            size = line
            break

    info["size"] = size

    # 4. Name extraction
    known_brands = [
        "trader joe's",
        "milsani",
        "goud gebakken",
        "cantolino",
        "steenbrugge",
        "molenland",
        "party gebak",
        "mama mancini",
        "de vleesmeesters",
        "bbq",
        "golden seafood",
        "mucci",
        "my vay",
        "Mucci",
    ]
    skip_words = ["boodschappenlijstje", "inhoud", "kg =", "l ="]
    potential_names = []
    seen_lines = set()

    for line in lines:
        lower = line.lower()
        if (
            line == price_line
            or "=" in lower
            or line in seen_lines
            or len(line) <= 2
            or any(skip in lower for skip in skip_words)
            or lower in known_brands
        ):
            continue
        if any(k in lower for k in size_keywords) and not any(
            c.isalpha() for c in line.replace(" ", "").replace("x", "").replace("+", "")
        ):
            continue
        seen_lines.add(line)
        potential_names.append(line)

    if potential_names:
        unique = list(dict.fromkeys(potential_names))
        descriptive_names = [name for name in unique if len(name) > 5]
        info["name"] = (
            max(descriptive_names, key=len) if descriptive_names else unique[0]
        )

    return info


def transform_entry(entry: dict) -> dict:
    result = {"n": "", "p": "", "o": "", "s": "", "i": ""}
    if "raw_text" in entry:
        parsed = parse_product_text(entry["raw_text"])
        result["n"] = parsed["name"]
        result["p"] = parsed["price"]
        result["s"] = parsed["size"]
        result["o"] = parsed["offer"]
    if "image" in entry and entry["image"]:
        result["i"] = entry["image"]
    return structured_with_category(entry, result)


def organize_json(data):
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict):
        data = [data]
    return [transform_entry(entry) for entry in data if isinstance(entry, dict)]


def process_file(input_file: str, output_file: str = None) -> list:
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = organize_json(data)
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved {len(result)} entries to: {output_file}")
        return result
    except FileNotFoundError:
        print(f"❌ File '{input_file}' not found")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return []


def main():
    process_file("merged_aldi.json", "../final_aldi.json")


if __name__ == "__main__":
    main()
