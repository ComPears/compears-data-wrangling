
import json


def convert_whole_prices_to_decimal(data):
    for item in data:
        price = item.get("p")
        if price and price.isdigit():  # whole number string like "85"
            item["p"] = f"0.{price.zfill(2)}"  # Ensure 2-digit format
    return data


def process_file(input_file, output_file):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated_data = convert_whole_prices_to_decimal(data)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Updated prices saved to: {output_file}")


# Run it
process_file("final.json", "dirk_all.json")




#######for converting to decimal