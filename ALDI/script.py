# script.py
import os
import sys
from importlib.util import spec_from_file_location, module_from_spec

def import_module_from_file(file_path):
    module_name = os.path.splitext(os.path.basename(file_path))[0]
    spec = spec_from_file_location(module_name, file_path)
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def run_in_directory(directory, func, *args, **kwargs):
    original_dir = os.getcwd()
    try:
        os.chdir(directory)
        return func(*args, **kwargs)
    finally:
        os.chdir(original_dir)

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_dir = os.path.join(script_dir, "Test")

    # Use absolute paths for everything
    aldi_results_dir = os.path.join(script_dir, "aldi_results")
    merged_json = os.path.join(script_dir, "merged_aldi.json")
    structured_json = os.path.join(script_dir, "structured_aldi.json")

    ensure_dir(aldi_results_dir)

    # STEP 1: Scraping
    print("=== STEP 1: Running Aldi scraper ===")
    main_module = import_module_from_file(os.path.join(script_dir, "main.py"))
    if hasattr(main_module, 'scrape_aldi_products'):
        from links import get_aldi_links
        os.chdir(script_dir)  # Ensure relative writes go to ALDI/
        main_module.scrape_aldi_products(get_aldi_links())
        print("✅ Scraping completed - results saved to aldi_results/")
    else:
        print("❌ Error: main.py doesn't have scrape_aldi_products")
        return

    # STEP 2: Merging JSON
    print("\n=== STEP 2: Merging JSON files ===")
    def run_mergejson():
        merge_module = import_module_from_file(os.path.join(script_dir, "mergejson.py"))
        if hasattr(merge_module, 'merge_json_files'):
            merge_module.merge_json_files(aldi_results_dir, merged_json)
            print(f"✅ Merging completed - results saved to {merged_json}")
        else:
            print("❌ Error: mergejson.py doesn't have merge_json_files")
    run_mergejson()

    # STEP 3: Remove patterns
    print("\n=== STEP 3: Removing patterns ===")
    def run_remove_patterns():
        remove_module = import_module_from_file(os.path.join(script_dir, "remove_patterns.py"))
        if hasattr(remove_module, 'clean_raw_text_in_file'):
            patterns = ["Barissimo\n\n", "Snack fan\n\n", "..."]
            remove_module.clean_raw_text_in_file(merged_json, patterns)
            print(f"✅ Patterns removed in {merged_json}")
        else:
            print("❌ Error: remove_patterns.py doesn't have clean_raw_text_in_file")
    run_remove_patterns()

    # STEP 4: Restructure
    print("\n=== STEP 4: Restructuring data ===")
    def run_restructure():
        restructure_module = import_module_from_file(os.path.join(script_dir, "restructure.py"))
        if hasattr(restructure_module, 'process_file'):
            restructure_module.process_file(merged_json, structured_json)
            print(f"✅ Restructured to {structured_json}")
        else:
            print("❌ Error: restructure.py doesn't have process_file")
    run_restructure()

    # STEP 5: Clean duplicates
    print("\n=== STEP 5: Cleaning duplicates ===")
    clean_module = import_module_from_file(os.path.join(script_dir, "clean_aldi.py"))
    if hasattr(clean_module, 'remove_duplicate_items_from_json'):
        clean_module.remove_duplicate_items_from_json(structured_json)
        print("✅ Duplicates removed from structured_aldi.json")
    else:
        print("❌ Error: clean_aldi.py doesn't have remove_duplicate_items_from_json")

    print("\n✅ PIPELINE COMPLETED!")
    print(f"Final output: {structured_json}")

if __name__ == "__main__":
    main()
