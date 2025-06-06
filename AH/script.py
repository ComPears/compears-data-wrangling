# run_pipeline.py
import os
import sys
import shutil
from importlib.util import spec_from_file_location, module_from_spec

def import_module_from_file(file_path):
    """Dynamically import a module from a file path."""
    module_name = os.path.splitext(os.path.basename(file_path))[0]
    spec = spec_from_file_location(module_name, file_path)
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def main():
    # Define paths to all scripts (assuming same directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    scripts = {
        'main': os.path.join(script_dir, "main.py"),
        'parse_all_json': os.path.join(script_dir, "parse_all_json.py"),
        'clean_ah': os.path.join(script_dir, "clean_ah.py")
    }

    # Create necessary directories
    os.makedirs("new_results", exist_ok=True)
    os.makedirs("raw_with_image_links", exist_ok=True)

    # Step 1: Run main.py (scraping)
    print("\n=== STEP 1: Running AH scraper ===")
    main_module = import_module_from_file(scripts['main'])
    if hasattr(main_module, 'scrape_ah_products'):
        from links_dictionary import get_ah_links
        ah_links = get_ah_links()
        for name, url in ah_links.items():
            print(f"\n🔄 Scraping category: {name}")
            main_module.scrape_ah_products(url, name)
        print("\n✅ Scraping completed - results saved to new_results/")
    else:
        print("❌ Error: main.py doesn't have scrape_ah_products function")
        return

    # Step 2: Prepare files for parsing
    print("\n=== STEP 2: Preparing files for parsing ===")
    # Move scraped files to raw_with_image_links folder
    for file in os.listdir("new_results"):
        if file.endswith(".json"):
            shutil.move(
                os.path.join("new_results", file),
                os.path.join("raw_with_image_links", file)
            )
    print("✅ Files moved to raw_with_image_links/")

    # Step 3: Run parse_all_json.py
    print("\n=== STEP 3: Parsing and merging JSON files ===")
    parse_module = import_module_from_file(scripts['parse_all_json'])
    if hasattr(parse_module, 'parse_product'):
        # The parse_all_json.py script runs automatically when imported
        # as it has code at module level that executes on import
        print("✅ Parsing completed - results saved to structured_all_merged.json")
    else:
        print("❌ Error: parse_all_json.py doesn't have parse_product function")
        return

    # Step 4: Run clean_ah.py
    print("\n=== STEP 4: Cleaning duplicates ===")
    clean_module = import_module_from_file(scripts['clean_ah'])
    if hasattr(clean_module, 'remove_duplicate_items_from_json'):
        clean_module.remove_duplicate_items_from_json("structured_all_merged.json")
        print("✅ Duplicate removal completed - final results in structured_all_merged.json")
    else:
        print("❌ Error: clean_ah.py doesn't have remove_duplicate_items_from_json function")
        return

    print("\n✅ PIPELINE COMPLETED SUCCESSFULLY!")
    print("Final structured and cleaned data available in: structured_all_merged.json")

if __name__ == "__main__":
    main()