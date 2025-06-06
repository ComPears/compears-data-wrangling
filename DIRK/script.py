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
        'separate': os.path.join(script_dir, "seperate.py"),
        'actieprobeer': os.path.join(script_dir, "actieprobeer.py"),
        'structure': os.path.join(script_dir, "structure.py"),
        'mergeit': os.path.join(script_dir, "mergeit.py"),
        'decimal_fix': os.path.join(script_dir, "decimal_fix.py"),
        'clean_dirk': os.path.join(script_dir, "clean_dirk.py")
    }

    # Step 1: Run main.py (scraping)
    print("=== STEP 1: Running main scraper ===")
    main_module = import_module_from_file(scripts['main'])
    if hasattr(main_module, 'product_data'):
        print(f"✅ Scraped {len(main_module.product_data)} items")
    else:
        print("⚠️ Main scraping completed (check JSONs/dirk.json)")

    # Step 2: Run separate.py
    print("\n=== STEP 2: Separating probeer/actie items ===")
    separate_module = import_module_from_file(scripts['separate'])
    if hasattr(separate_module, 'split_items_by_keywords'):
        separate_module.split_items_by_keywords("DIRK/JSONs/dirk.json", ["PROBEER PRIJS", "ACTIE"])

    # Step 3: Run actieprobeer.py
    print("\n=== STEP 3: Processing actie/probeer items ===")
    actieprobeer_module = import_module_from_file(scripts['actieprobeer'])
    if hasattr(actieprobeer_module, 'parse_entry'):
        print("✅ Actie/probeer items processed")

    # Step 4: Run structure.py
    print("\n=== STEP 4: Structuring main items ===")
    structure_module = import_module_from_file(scripts['structure'])
    if hasattr(structure_module, 'parse_entry'):
        print("✅ Main items structured")

    # Step 5: Run mergeit.py
    print("\n=== STEP 5: Merging structured data ===")
    mergeit_module = import_module_from_file(scripts['mergeit'])
    if hasattr(mergeit_module, 'data3'):
        print(f"✅ Merged {len(mergeit_module.data3)} items")

    # Step 6: Run decimal_fix.py
    print("\n=== STEP 6: Fixing decimal prices ===")
    decimal_fix_module = import_module_from_file(scripts['decimal_fix'])
    if hasattr(decimal_fix_module, 'process_file'):
        decimal_fix_module.process_file("DIRK/JSONs/final.json", "./dirk_all.json")

    # Step 7: Run clean_dirk.py
    print("\n=== STEP 7: Cleaning duplicates ===")
    clean_dirk_module = import_module_from_file(scripts['clean_dirk'])
    if hasattr(clean_dirk_module, 'remove_duplicate_items_from_json'):
        clean_dirk_module.remove_duplicate_items_from_json("dirk_all.json")

    print("\n✅ PIPELINE COMPLETED SUCCESSFULLY!")
    print("Final output: dirk_all.json")

if __name__ == "__main__":
    main()