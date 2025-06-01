import json
import re

# Load input data
with open("lidl.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Patterns
offer_keywords = [
    "actie",
    "van",
    "korting",
    "1+1",
    "gratis",
    "probeer prijs",
    "tot",
    "-",
]

# Add patterns for store/date related phrases
store_date_patterns = [
    r"alleen in de winkel vanaf \d{2}/\d{2}",
    r"alleen in de winkel",
    r"vanaf \d{2}/\d{2}",
    r"vanaf \d{1,2}\s+[a-zA-Z]+",  # e.g. "vanaf 28 mei"
    r"geldig tot \d{2}/\d{2}",
    r"geldig vanaf \d{2}/\d{2}",
    r"verkrijgbaar vanaf \d{2}/\d{2}",
    r"-\d+%\s*-\s*\d{2}/\d{2}",  # e.g. "-30% - 09/06"
    r"prijs\s+ca\.\s+\d+\s*g:\s*€\.?",  # e.g. "Prijs ca. 350 g: €."
    r"-€\d+\.-",  # e.g. "-€1.-"
    r"\d{2}/\d{2}\s*-\s*\d{2}/\d{2}",  # e.g. "26/05 - 01/06"
    r"prijs\s+ca\.",  # e.g. "prijs ca."
    r"\s*:\s*€\.?",  # e.g. ": €."
    r"-Є\d+\.-",  # e.g. "-Є1.-"
    r"\b(?:KILO|GRAM|LITER|STUKS)\b!?",  # Remove unit indicators
    r"\s*!+",  # Remove exclamation marks
    r"(?<=[0-9])\s*(?:G|KG|ML|L|CL)\b",  # Remove units after numbers
]

unit_pattern = re.compile(
    r"^\d+([.,]?\d+)?\s?(g|kg|ml|l|cl|liter|stuks?|x.*)$", re.IGNORECASE
)
price_pattern = re.compile(r"^\d+$")


def parse_entry(entry):
    raw_text = entry["raw_text"]
    raw_lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    offer_lines, size, price = [], "", ""

    # Join everything for pattern matching
    full_text = " ".join(raw_lines)

    # 1. Extract offer lines
    for line in raw_lines:
        if any(k in line.lower() for k in offer_keywords):
            offer_lines.append(line)
    offer = " ".join(offer_lines)
    raw_lines = [line for line in raw_lines if line not in offer_lines]

    # 2. Extract all price-like values and pick the lowest one
    prices = re.findall(r"\d+[.,]\d{2}", full_text)
    if prices:
        price = min([float(p.replace(",", ".")) for p in prices])
        price = f"{price:.2f}"

    # 3. Extract size
    size_match = re.search(
        r"\b(per\s+\w+|\d+\s*[xX]\s*\d+\s*(?:g|kg|ml|l|cl|stuks?)|"
        r"\d+\s?(g|kg|ml|l|cl|x\s?\d+.*|stuks?))",
        full_text,
        re.IGNORECASE
    )
    if size_match:
        size = size_match.group().strip()
        # Standardize the format
        size = re.sub(r'\s+', ' ', size)  # normalize spaces
        size = re.sub(r'([0-9])([xX])([0-9])', r'\1 x \3', size)  # add spaces around x
        size = size.upper()  # uppercase for consistency

    # 4. Clean name (remove price, size, and offer from text)
    clean_text = full_text
    for part in prices + ([offer] if offer else []) + ([size] if size else []):
        clean_text = clean_text.replace(str(part), "")
    
    # Remove offer keywords from the name
    for keyword in offer_keywords:
        clean_text = re.sub(rf'\b{re.escape(keyword)}\b', '', clean_text, flags=re.IGNORECASE)
    
    # Remove store/date related phrases
    for pattern in store_date_patterns:
        clean_text = re.sub(pattern, '', clean_text, flags=re.IGNORECASE)
    
    # Additional cleaning
    clean_text = re.sub(r'[-−]?[€Є]\d+\.?-?', '', clean_text)  # Remove price indicators
    clean_text = re.sub(r'\bRAM\b', '', clean_text, flags=re.IGNORECASE)  # Remove RAM
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()  # Clean up spaces
    
    # De-duplicate name
    words = clean_text.split()
    if len(words) >= 2:
        seen = set()
        unique_words = []
        for word in words:
            if word.lower() not in seen:
                unique_words.append(word)
                seen.add(word.lower())
        clean_text = ' '.join(unique_words)

    return {
        "n": clean_text.strip(),
        "p": price,
        "o": offer.strip(),
        "s": size,
        "l": entry.get("image", ""),
    }

structured = [parse_entry(entry) for entry in data]

with open("lidl_structured.json", "w", encoding="utf-8") as f:
    json.dump(structured, f, indent=2, ensure_ascii=False)

print("✅ Done! Saved to 'lidl_structured.json'")
