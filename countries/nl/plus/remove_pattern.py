import json, os


def clean_raw_text_in_file(file_path, patterns_to_remove):
    if not os.path.exists(file_path):
        return print(f"❌ File not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data if isinstance(data, list) else []:
            if "raw_text" in item:
                for pattern in patterns_to_remove:
                    if pattern in item["raw_text"]:
                        item["raw_text"] = item["raw_text"].replace(pattern, "")

        base, ext = os.path.splitext(file_path)
        output_file = f"{base}{ext}"

        with open("plus.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✅ Cleaned file saved to: {output_file}")

    except Exception as e:
        print(f"⚠️ Error processing file: {e}")


# Example usage
if __name__ == "__main__":
    # List of patterns to remove
    patterns = ["Uit de keuken van"]
    clean_raw_text_in_file("plus.json", patterns)
