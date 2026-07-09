#!/usr/bin/env bash
# Run the same steps as CI for one store. Usage: test_store_pipeline.sh <store-slug>
set -euo pipefail

STORE="${1:?Store slug required (albert-heijn|aldi|dirk|plus|lidl|coop|jumbo)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
LOG_DIR="${ROOT}/.local-test-logs"
mkdir -p "$LOG_DIR"

LOG_FILE="${LOG_DIR}/${STORE}.log"
START=$(date +%s)

run_step() {
  echo "=== $* ===" | tee -a "$LOG_FILE"
  "$@" >>"$LOG_FILE" 2>&1
}

{
  echo "STORE=${STORE}"
  echo "START=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "ROOT=${ROOT}"
} >"$LOG_FILE"

cd "$ROOT"
run_step $PYTHON -m pip install -q -r requirements.txt
run_step $PYTHON scripts/run_store_pipeline.py --store "$STORE"

cd "$ROOT"
run_step $PYTHON scripts/sanitize_all_stores.py
run_step $PYTHON scripts/validate_products.py
run_step $PYTHON scripts/validate_store_output.py --store "$STORE"
run_step $PYTHON scripts/prune_stale_artifacts.py

OUT=$($PYTHON -c "
from config.paths import catalog_rel_path, load_stores_config
cfg = load_stores_config()
for slug in cfg['countries']['nl']['stores']:
    if slug == '$STORE':
        print(catalog_rel_path('nl', slug))
        break
")

END=$(date +%s)
DURATION=$((END - START))

if [[ -n "$OUT" && -f "$ROOT/$OUT" ]]; then
  COUNT=$($PYTHON -c "import json; print(len(json.load(open('$ROOT/$OUT'))))")
else
  COUNT=0
fi

echo "RESULT=PASS STORE=${STORE} DURATION=${DURATION}s PRODUCTS=${COUNT} OUTPUT=${OUT}" | tee -a "$LOG_FILE"
echo "PASS ${STORE} ${DURATION}s ${COUNT} products"
