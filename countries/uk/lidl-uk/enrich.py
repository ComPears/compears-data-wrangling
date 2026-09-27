"""Recover explicit pack sizes before structuring the daily Lidl catalog."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
sys.path.insert(0, str(HERE.parents[2]))

from lidl_details import enrich_pack_sizes
from scrape_utils import write_json_atomic


def main():
    path = HERE / "lidl_uk.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    enrich_pack_sizes(rows)
    write_json_atomic(path, rows)


if __name__ == "__main__":
    main()
