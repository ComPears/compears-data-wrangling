# script.py
import os
import sys
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
        'structure': os.path.join(script_dir, "structure.py"),
        'clean_coop': os.path.join(script_dir, "clean_coop.py")
    }

    # Step 1: Run main.py (scraping)
    print("=== STEP 1: Running Coop scraper ===")
    main_module = import_module_from_file(scripts['main'])
    if hasattr(main_module, 'scrape_coop_products'):
        # Import links from links.py in the same directory
        from links import links
        main_module.scrape_coop_products(links, output_file="coop.json")
        print("✅ Scraping completed - results saved to coop.json")
    else:
        print("❌ Error: main.py doesn't have scrape_coop_products function")
        return

    # Step 2: Run structure.py
    print("\n=== STEP 2: Structuring scraped data ===")
    structure_module = import_module_from_file(scripts['structure'])
    if hasattr(structure_module, 'parse_entry'):
        # The structure.py script runs automatically when imported
        print("✅ Data structuring completed - results saved to coop_structured.json")
    else:
        print("❌ Error: structure.py doesn't have parse_entry function")
        return

    # Step 3: Run clean_coop.py
    print("\n=== STEP 3: Cleaning duplicates ===")
    clean_coop_module = import_module_from_file(scripts['clean_coop'])
    if hasattr(clean_coop_module, 'remove_duplicate_items_from_json'):
        clean_coop_module.remove_duplicate_items_from_json("coop_structured.json")
        print("✅ Duplicate removal completed - final results in coop_structured.json")
    else:
        print("❌ Error: clean_coop.py doesn't have remove_duplicate_items_from_json function")
        return

    print("\n✅ PIPELINE COMPLETED SUCCESSFULLY!")
    print("Final structured and cleaned data available in: coop_structured.json")

if __name__ == "__main__":
    main()