import os
import json
import glob


def merge_json_files(folder_path, output_file):
    """
    Merges all JSON files in the specified folder into a single JSON file.

    Args:
        folder_path: Path to the folder containing JSON files
        output_file: Name of the output merged JSON file
    """
    # Make sure the folder path exists
    if not os.path.exists(folder_path):
        print(f"Error: The folder '{folder_path}' does not exist.")
        return

    # Initialize an empty list to store all the data
    merged_data = []

    # Get all JSON files in the folder
    json_files = glob.glob(os.path.join(folder_path, "*.json"))

    # Check if any JSON files were found
    if not json_files:
        print(f"No JSON files found in '{folder_path}'.")
        return

    print(f"Found {len(json_files)} JSON files to merge.")

    # Process each JSON file
    for file_path in json_files:
        try:
            with open(file_path, "r") as f:
                # Load JSON data
                data = json.load(f)

                # If the data is a list, extend the merged_data list
                if isinstance(data, list):
                    merged_data.extend(data)
                # If the data is a dictionary, append it to the merged_data list
                elif isinstance(data, dict):
                    merged_data.append(data)

                print(f"Processed: {os.path.basename(file_path)}")

        except json.JSONDecodeError:
            print(f"Error: Could not parse '{file_path}' as JSON. Skipping.")
        except Exception as e:
            print(f"Error processing '{file_path}': {str(e)}")

    # Write the merged data to the output file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, indent=4,ensure_ascii=False)

    print(f"Successfully merged {len(json_files)} JSON files into '{output_file}'.")


# Example usage
if __name__ == "__main__":
    # Replace these with your actual paths
    folder_with_json_files = "JSONs"
    output_json_file = "Jumbo.json"

    merge_json_files(folder_with_json_files, output_json_file)
