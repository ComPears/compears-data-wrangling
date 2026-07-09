import glob
import json
import sys
from pathlib import Path

JSONS_DIR = Path(__file__).resolve().parent / "JSONs"
OUTPUT_FILE = Path(__file__).resolve().parent / "Jumbo.json"
MIN_INPUT_FILES = 10


def merge_json_files(folder_path: Path, output_file: Path) -> None:
    if not folder_path.exists():
        print(f"Error: The folder '{folder_path}' does not exist.")
        sys.exit(1)

    merged_data: list[dict] = []
    json_files = sorted(glob.glob(str(folder_path / "*.json")))

    if len(json_files) < MIN_INPUT_FILES:
        print(
            f"Error: expected at least {MIN_INPUT_FILES} JSON files in "
            f"'{folder_path}', found {len(json_files)}."
        )
        sys.exit(1)

    print(f"Found {len(json_files)} JSON files to merge.")

    for file_path in json_files:
        try:
            with open(file_path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                merged_data.extend(data)
            elif isinstance(data, dict):
                merged_data.append(data)
            print(f"Processed: {Path(file_path).name}")
        except json.JSONDecodeError:
            print(f"Error: Could not parse '{file_path}' as JSON. Skipping.")
        except Exception as err:
            print(f"Error processing '{file_path}': {err}")

    if not merged_data:
        print("Error: merged dataset is empty.")
        sys.exit(1)

    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(merged_data, handle, indent=4, ensure_ascii=False)

    print(
        f"Successfully merged {len(json_files)} JSON files into "
        f"'{output_file}' ({len(merged_data)} products)."
    )


if __name__ == "__main__":
    merge_json_files(JSONS_DIR, OUTPUT_FILE)
