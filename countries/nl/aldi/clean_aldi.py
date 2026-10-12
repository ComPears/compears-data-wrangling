import json


def remove_duplicate_items_from_json(input_file, key="n"):
    # Load JSON data from file
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("Initial items in list: {}".format(len(data)))

    seen = set()
    cleaned_data = []

    for item in data:
        name = item.get(key, "").strip()

        # Skip items with empty or missing name
        if not name:
            continue

        # Identically named products can have different pack sizes. Preserve
        # retailer identity and pack variants for price-per-unit comparison.
        identity = item.get("productUrl") or item.get("retailerProductId") or (
            name.casefold(), str(item.get("s") or "").casefold(), str(item.get("bn") or "").casefold()
        )
        if identity not in seen:
            seen.add(identity)
            cleaned_data.append(item)

    print(
        "Total duplicates removed: {}, Total items: {}, Final items: {}".format(
            len(data) - len(cleaned_data), len(data), len(cleaned_data)
        )
    )
    print("Final items in list: {}".format(len(cleaned_data)))

    # Save cleaned data to output JSON
    with open(input_file, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, indent=2, ensure_ascii=False)

    return cleaned_data


if __name__ == "__main__":
    remove_duplicate_items_from_json("structured_aldi.json")
