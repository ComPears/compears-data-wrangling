import json, os


def split_items_by_keywords(file_path, keywords):
    if not os.path.exists(file_path):
        return print(f"❌ File not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return print("⚠️ Expected a list of items in the JSON file.")

        matched_items = []
        remaining_items = []

        for item in data:
            raw_text = item.get("raw_text", "")
            if any(keyword in raw_text for keyword in keywords):
                matched_items.append(item)
            else:
                remaining_items.append(item)

        base, ext = os.path.splitext(file_path)
        keywords_clean = "_".join(k.replace(" ", "_").lower() for k in keywords)
        matched_file = f"{base}_{keywords_clean}{ext}"

        # Save matched items to a separate file
        with open(matched_file, "w", encoding="utf-8") as f:
            json.dump(matched_items, f, indent=2, ensure_ascii=False)

        # Overwrite original file with remaining items
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(remaining_items, f, indent=2, ensure_ascii=False)

        print(
            f"✅ Moved {len(matched_items)} items containing keywords {keywords} to: {matched_file}"
        )
        print(f"✅ Remaining {len(remaining_items)} items saved to: {file_path}")

    except Exception as e:
        print(f"⚠️ Error processing file: {e}")


# Example usage
if __name__ == "__main__":
    # PROBEER PRIJS & ACTIE
    split_items_by_keywords("JSONs/dirk.json", ["PROBEER PRIJS", "ACTIE"])
