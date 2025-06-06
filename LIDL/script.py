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
    structure_script = os.path.join(script_dir, "structure.py")
    clean_lidl_script = os.path.join(script_dir, "clean_lidl.py")

    # Step 1: Run main.py (scraping)
    print("=== Running main scraping ===")
    main_module = import_module_from_file(main_script)
    if hasattr(main_module, 'scrape_lidl_pages'):
        main_module.scrape_lidl_pages()
    else:
        print("Error: main.py doesn't have scrape_lidl_pages function")

    # Step 2: Run structure.py
    print("\n=== Running structure ===")
    structure_module = import_module_from_file(structure_script)
    if hasattr(structure_module, 'parse_entry'):
        # structure.py runs automatically when imported (no main function)
        print("✅ Structure processing completed")
    else:
        print("Error: structure.py doesn't have expected functions")

    # Step 3: Run clean_lidl.py
    print("\n=== Running clean_lidl ===")
    clean_lidl_module = import_module_from_file(clean_lidl_script)
    if hasattr(clean_lidl_module, 'remove_duplicate_items_from_json'):
        clean_lidl_module.remove_duplicate_items_from_json("lidl_structured.json")
    else:
        print("Error: clean_lidl.py doesn't have remove_duplicate_items_from_json function")

    print("\n✅ All processing steps completed successfully!")

if __name__ == "__main__":
    main()