import json
import os
import subprocess
from pathlib import Path

# Configuration - Update these paths as needed
scripts_config = [
    {
        # "script_path": "AH/script.py",  
        "store_name": "ah",               
        "store_url": "https://www.ah.nl/producten/product/",                
        "store_favicon": "https://www.ah.nl/favicon.ico",             
        "output_json": "AH/structured_all_merged.json" 
    },
     {
        # "script_path": "ALDI/script.py",  
        "store_name": "aldi",               
        "store_url": "https://www.aldi.nl/producten.html",                
        "store_favicon": "https://www.aldi.nl/favicon.ico",             
        "output_json": "ALDI/structured_aldi.json" 
    },
     {
        # "script_path": "DIRK/script.py",  
        "store_name": "dirk",               
        "store_url": "https://www.dirk.nl/boodschappen/",                
        "store_favicon": "https://www.dirk.nl/favicon.ico",             
        "output_json": "DIRK/dirk_all.json" 
    }
]
supermarket_json_path = "supermarkets_merged.json"  # Final output file

# def run_script(script_path):
#     """Run a Python script in its own directory and return True if successful."""
#     script_dir = os.path.dirname(script_path) or "."
#     script_file = os.path.basename(script_path)
    
#     try:
#         # Run the script in its own directory to ensure correct relative paths
#         subprocess.run(["python", script_file], cwd=script_dir, check=True)
#         return True
#     except subprocess.CalledProcessError as e:
#         print(f"❌ Error running {script_path}: {e}")
#         return False

def load_json(file_path):
    """Load JSON data from a file, return empty dict if file doesn't exist."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"⚠️ JSON file not found or invalid: {file_path}")
        return {}

def main():
    supermarket_data = []

    for script in scripts_config:
        # 1. Run the script (in its own directory)
        # print(f"▶ Running {script['script_path']}...")
        # success = run_script(script['script_path'])
        
        # if not success:
        #     print(f"⏩ Skipping {script['store_name']} due to script failure.")
        #     continue

        # 2. Load the generated JSON (from the specified path)
        script_data = load_json(script["output_json"])

        # 3. Add to supermarket_data
        entry = {
            "n": script["store_name"],
            "u": script["store_url"],
            "i": script["store_favicon"],
            "d": script_data
        }
        supermarket_data.append(entry)

    # 4. Save to supermarkets_merged.json
    with open(supermarket_json_path, 'w', encoding='utf-8') as f:
        json.dump(supermarket_data, f, indent=4, ensure_ascii=False)

    print(f"✅ Successfully updated {supermarket_json_path}")

if __name__ == "__main__":
    main()