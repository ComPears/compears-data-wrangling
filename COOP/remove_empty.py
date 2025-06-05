import json

file_path = "coop.json"  # Replace with your actual JSON file path

# Load the JSON data
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Filter out entries with empty 'raw_text'
filtered_data = [item for item in data if item.get("raw_text")]

# Overwrite the original file with filtered data
with open(file_path, "w", encoding="utf-8") as f:
    json.dump(filtered_data, f, ensure_ascii=False, indent=2)

print(f"Updated {file_path} with {len(filtered_data)} valid entries.")
