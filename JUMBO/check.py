import json


def check_and_store_partial_name_offer_matches():
    with open("Jumbo_structured.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    matches = []

    for item in data:
        name = item.get("n", "").strip()
        offer = item.get("o", "").strip()
        if offer.startswith(name):
            matches.append(item)

    if matches:
        with open("matched_entries.json", "w", encoding="utf-8") as out_file:
            json.dump(matches, out_file, indent=2, ensure_ascii=False)
        print(f"{len(matches)} partial matches saved to 'matched_entries.json'.")
    else:
        print("No partial matches found.")


# Run the partial match check and store
check_and_store_partial_name_offer_matches()
