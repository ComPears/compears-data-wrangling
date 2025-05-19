import json
import os
import glob
import re


def extract_product_info(raw_text, image_url):
    lines = raw_text.split("\n")
    product = {"n": "", "p": "", "o": "", "s": "", "i": image_url}

    if len(lines) >= 3:
        product["n"] = f"{lines[0].strip()} {lines[2].strip()}"

    for i, line in enumerate(lines):
        if re.match(r"\d+\.\d+|\d+", line.strip()) and i > 0:
            product["p"] = line.strip()
            break

    for line in lines:
        if re.search(r"(kg|g|ml|l|stuks|tabs|doekjes|stuk)", line, re.IGNORECASE):
            if not re.search(r"[a-z]+ = \d+\.\d+", line, re.IGNORECASE):
                product["s"] = line.strip()
                break

    for line in lines:
        if re.search(
            r"(aanbieding|korting|actie|sale|In de aanbieding vanaf \d+\.\d+)",
            line,
            re.IGNORECASE,
        ):
            product["o"] = line.strip()
            break

    return product


def extract_product_data(input_path, output_file):
    if not os.path.exists(input_path):
        print(f"Error: Path '{input_path}' does not exist.")
        return

    files = (
        [input_path]
        if input_path.endswith(".json")
        else glob.glob(os.path.join(input_path, "*.json"))
    )

    if not files:
        print(f"No JSON files found in '{input_path}'.")
        return

    all_products = []

    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                for item in data:
                    if "raw_text" in item and "image" in item:
                        all_products.append(
                            extract_product_info(item["raw_text"], item["image"])
                        )

            print(f"Processed: {os.path.basename(file)}")

        except Exception as e:
            print(f"Error processing '{file}': {e}")

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_products, f, indent=2, ensure_ascii=False)
        print(f"Output saved to {output_file}")
    except Exception as e:
        print(f"Error writing output file: {e}")


if __name__ == "__main__":
    input_path = "./merged_aldi.json"  # can be a file or folder
    output_file = "./final_aldi.json"
    extract_product_data(input_path, output_file)
