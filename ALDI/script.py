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

def run_in_directory(directory, func, *args, **kwargs):
    """Run a function in a specific directory and return to original dir."""
    original_dir = os.getcwd()
    try:
        os.chdir(directory)
        return func(*args, **kwargs)
    finally:
        os.chdir(original_dir)

# ... (keep the imports and helper functions unchanged)

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_dir = os.path.join(script_dir, "Test")

    # Step 1: Scraping (unchanged)
    print("=== STEP 1: Running Aldi scraper ===")
    main_module = import_module_from_file(os.path.join(script_dir, "main.py"))
    if hasattr(main_module, 'scrape_aldi_products'):
        from links import get_aldi_links
        main_module.scrape_aldi_products(get_aldi_links())
        print("✅ Scraping completed - results saved to aldi_results/")
    else:
        print("❌ Error: main.py doesn't have scrape_aldi_products function")
        return

    # Step 2: Merge JSONs directly into root dir (modified)
    print("\n=== STEP 2: Merging JSON files ===")
    def run_mergejson():
        merge_module = import_module_from_file("mergejson.py")
        if hasattr(merge_module, 'merge_json_files'):
            # Output to root directory instead of Test/
            merge_module.merge_json_files(
                "../aldi_results",  # Input dir (relative to Test/)
                os.path.join("..", "merged_aldi.json")  # Output path
            )
            print("✅ Merging completed - results saved to root dir/merged_aldi.json")
        else:
            print("❌ Error: mergejson.py doesn't have merge_json_files function")
    run_in_directory(test_dir, run_mergejson)

    # Step 3: Remove patterns from root dir's merged file (modified)
    print("\n=== STEP 3: Removing patterns ===")
    def run_remove_patterns():
        remove_module = import_module_from_file("remove_patterns.py")
        if hasattr(remove_module, 'clean_raw_text_in_file'):
            patterns = ["Barissimo\n\n", "Snack fan\n\n", "..."]  # Your patterns
            # Operate on the root dir's merged file
            remove_module.clean_raw_text_in_file(
                os.path.join("..", "merged_aldi.json"),  # Input path
                patterns
            )
            print("✅ Pattern removal completed (root dir/merged_aldi.json)")
        else:
            print("❌ Error: remove_patterns.py doesn't have clean_raw_text_in_file function")
    run_in_directory(test_dir, run_remove_patterns)

    # Step 4: Restructure (now reads/writes directly to root dir)
    print("\n=== STEP 4: Restructuring data ===")
    def run_restructure():
        restructure_module = import_module_from_file("restructure.py")
        if hasattr(restructure_module, 'process_file'):
            # Read from root dir, write to root dir
            restructure_module.process_file(
                os.path.join("..", "merged_aldi.json"),  # Input
                os.path.join("..", "structured_aldi.json")  # Output
            )
            print("✅ Restructuring completed - results in root dir/structured_aldi.json")
        else:
            print("❌ Error: restructure.py doesn't have process_file function")
    run_in_directory(test_dir, run_restructure)

    # Step 5: Clean duplicates (unchanged, already operates in root dir)
    print("\n=== STEP 5: Cleaning duplicates ===")
    clean_module = import_module_from_file(os.path.join(script_dir, "clean_aldi.py"))
    if hasattr(clean_module, 'remove_duplicate_items_from_json'):
        clean_module.remove_duplicate_items_from_json("structured_aldi.json")
        print("✅ Duplicate removal completed")
    else:
        print("❌ Error: clean_aldi.py doesn't have remove_duplicate_items_from_json function")

    print("\n✅ PIPELINE COMPLETED!")
    print(f"Final output: {os.path.join(script_dir, 'structured_aldi.json')}")

if __name__ == "__main__":
    main()