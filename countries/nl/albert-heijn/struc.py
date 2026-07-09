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


def re_structure(input_file: str, output_file: str):
    # Load the raw scraped file
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Keyword and regex patterns
    offer_keywords = [
        "nu voor",
        "korting",
        "actie",
        "van ",
        "voor ",
        "deal",
        "2 voor",
        "3 voor",
        "aanbieding",
        "probeer prijs",
        "sale",
        "special",
        "2 + 1 GRATIS",
        "1 + 1 GRATIS",
        "2 VOOR",
        "3 VOOR",
        "4 VOOR",
        "6 VOOR",
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
        r"\b\d+([.,]?\d+)?\s?(g|kg|ml|l|cl|stuks?|stuk\(s\)|x\s?\d+.*)\b", re.IGNORECASE
    )
    price_pattern = re.compile(r"\d+[.,]\d{2}")

    def parse_entry(entry):
        raw_lines = [
            line.strip() for line in entry["raw_text"].split("\n") if line.strip()
        ]
        all_prices = re.findall(price_pattern, entry["raw_text"])

        name = ""
        offer = ""
        regular_price = ""
        offer_price = ""

        # Identify offer lines and extract offer price
        offer_lines = []
        for line in raw_lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in offer_keywords):
                offer_lines.append(line)
                line_prices = re.findall(price_pattern, line)
                if line_prices:
                    offer_price = line_prices[0].replace(",", ".")

        # Find product name
        for line in raw_lines:
            line_lower = line.lower()
            is_offer_line = any(keyword in line_lower for keyword in offer_keywords)
            is_price_only = re.match(r"^\d+[.,]\d{2}$", line.strip())
            is_size_only = unit_pattern.match(line.strip()) and not any(
                char.isalpha() for char in line if char not in "gkmlxstuc()"
            )
            if (
                not is_offer_line
                and not is_price_only
                and not is_size_only
                and line.strip()
            ):
                name = line.strip()
                break

        # Determine regular price
        if len(all_prices) >= 2 and offer_price:
            remaining_prices = [
                p for p in all_prices if p.replace(",", ".") != offer_price
            ]
            if remaining_prices:
                regular_price = remaining_prices[0].replace(",", ".")
        elif len(all_prices) == 1 and not offer_price:
            regular_price = all_prices[0].replace(",", ".")
        elif len(all_prices) >= 1 and not offer_price:
            regular_price = (
                f"{max([float(p.replace(',', '.')) for p in all_prices]):.2f}"
            )

        offer = " ".join(offer_lines) if offer_lines else ""

        size = ""
        for line in raw_lines:
            match = unit_pattern.search(line)
            if match:
                size = match.group()
                break

        image = entry.get("image", "")
        if image == "/assets/img/not_available.svg":
            image = ""

        return structured_with_category(
            entry,
            {
                "n": name,
                "o": offer if offer else "",
                "p": regular_price,
                "s": size,
                "l": image,
            },
        )

    structured = [parse_entry(entry) for entry in data]

    # Save to file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False)

    print(f"✅ Done! Structured output saved to '{output_file}'")


if __name__ == "__main__":
    re_structure("AH.json", "structured_all_merged.json")
