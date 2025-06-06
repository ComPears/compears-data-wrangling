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
    # Define the paths to the original files (assuming they're in the same directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(script_dir, "main.py")
    merge_script = os.path.join(script_dir, "merge.py")
    structure_script = os.path.join(script_dir, "structure.py")
    clean_jumbo_script = os.path.join(script_dir, "clean_jumbo.py")

    # Step 1: Run main.py (scraping)
    print("\n=== STEP 1: Running main scraping ===")
    main_module = import_module_from_file(main_script)
    if hasattr(main_module, 'scrape_jumbo_products'):
        from links import links  # Import links from the links.py file
        main_module.scrape_jumbo_products(links)
    else:
        print("Error: main.py doesn't have scrape_jumbo_products function")
        return

    # Step 2: Run merge.py
    print("\n=== STEP 2: Merging JSON files ===")
    merge_module = import_module_from_file(merge_script)
    if hasattr(merge_module, 'merge_json_files'):
        merge_module.merge_json_files("JSONs", "Jumbo.json")
    else:
        print("Error: merge.py doesn't have merge_json_files function")
        return

    # Step 3: Run structure.py
    print("\n=== STEP 3: Structuring data ===")
    structure_module = import_module_from_file(structure_script)
    if hasattr(structure_module, 'parse_entry'):
        # structure.py runs automatically when imported (no main function needed)
        print("✅ Structure processing completed")
    else:
        print("Error: structure.py doesn't have parse_entry function")
        return

    # Step 4: Run clean_jumbo.py
    print("\n=== STEP 4: Cleaning duplicates ===")
    clean_jumbo_module = import_module_from_file(clean_jumbo_script)
    if hasattr(clean_jumbo_module, 'remove_duplicate_items_from_json'):
        clean_jumbo_module.remove_duplicate_items_from_json("jumbo_structured.json")
    else:
        print("Error: clean_jumbo.py doesn't have remove_duplicate_items_from_json function")
        return

    print("\n✅ All processing steps completed successfully!")
    print("Final output saved to: jumbo_structured.json")

if __name__ == "__main__":
    main()