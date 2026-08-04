from pathlib import Path
import sys

SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from structure_catalog import structure_file  # noqa: E402

HERE = Path(__file__).resolve().parent
structure_file(HERE / "rewe.json", HERE / "rewe_structured.json")
