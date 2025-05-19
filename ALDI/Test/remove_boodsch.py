import json, os


def clean_raw_text_in_file(file_path):
    if not os.path.exists(file_path):
        return print(f"❌ File not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data if isinstance(data, list) else []:
            if "raw_text" in item:
                item["raw_text"] = item["raw_text"].replace("Barissimo\n\n", "")

        base, ext = os.path.splitext(file_path)
        output_file = f"{base}{ext}"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✅ Cleaned file saved to: {output_file}")

    except Exception as e:
        print(f"⚠️ Error processing file: {e}")


# Example usage
if __name__ == "__main__":
    clean_raw_text_in_file("merged_aldi.json")
