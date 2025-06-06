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
    # Define the paths to the original files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(script_dir, "main.py")
    remove_pattern_script = os.path.join(script_dir, "remove_pattern.py")
    fix_script = os.path.join(script_dir, "fix.py")
    clean_plus_script = os.path.join(script_dir, "clean_plus.py")

    # Step 1: Run main.py (scraping)
    print("=== Running main scraping ===")
    main_module = import_module_from_file(main_script)
    if hasattr(main_module, 'scrape_plus_products'):
        from links import links  # Import links from the links.py file
        main_module.scrape_plus_products(links)
    else:
        print("Error: main.py doesn't have scrape_plus_products function")

    # Step 2: Run remove_pattern.py
    print("\n=== Running remove_pattern ===")
    remove_pattern_module = import_module_from_file(remove_pattern_script)
    if hasattr(remove_pattern_module, 'clean_raw_text_in_file'):
        patterns = ["Uit de keuken van"]  # Patterns to remove
        remove_pattern_module.clean_raw_text_in_file("plus.json", patterns)
    else:
        print("Error: remove_pattern.py doesn't have clean_raw_text_in_file function")

    # Step 3: Run fix.py
    print("\n=== Running fix ===")
    fix_module = import_module_from_file(fix_script)
    if hasattr(fix_module, 'main'):
        fix_module.main()
    else:
        print("Error: fix.py doesn't have main function")

    # Step 4: Run clean_plus.py
    print("\n=== Running clean_plus ===")
    clean_plus_module = import_module_from_file(clean_plus_script)
    if hasattr(clean_plus_module, 'remove_duplicate_items_from_json'):
        clean_plus_module.remove_duplicate_items_from_json("structured_plus.json")
    else:
        print("Error: clean_plus.py doesn't have remove_duplicate_items_from_json function")

    print("\n✅ All processing steps completed successfully!")

if __name__ == "__main__":
    main()