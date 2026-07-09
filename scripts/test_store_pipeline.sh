#!/usr/bin/env bash
# Run the same steps as CI for one store. Usage: test_store_pipeline.sh <STORE>
set -euo pipefail

STORE="${1:?Store name required (AH|ALDI|DIRK|PLUS|LIDL|COOP|JUMBO)}"
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
$PYTHON -m pip install -q -r requirements.txt

case "$STORE" in
  AH)
    cd AH
    run_step $PYTHON main.py
    run_step $PYTHON merge.py
    run_step $PYTHON struc.py
    run_step $PYTHON clean_ah.py
    OUT="AH/structured_all_merged.json"
    ;;
  ALDI)
    if ! $PYTHON -m playwright install chromium >/dev/null 2>&1; then true; fi
    cd ALDI
    run_step $PYTHON main.py
    run_step $PYTHON mergejson.py
    run_step $PYTHON remove_patterns.py
    run_step $PYTHON restructure.py
    run_step $PYTHON clean_aldi.py
    OUT="ALDI/structured_aldi.json"
    ;;
  DIRK)
    if ! $PYTHON -m playwright install chromium >/dev/null 2>&1; then true; fi
    cd DIRK
    run_step $PYTHON main.py
    run_step $PYTHON seperate.py
    run_step $PYTHON actieprobeer.py
    run_step $PYTHON structure.py
    run_step $PYTHON mergeit.py
    run_step $PYTHON decimal_fix.py
    run_step $PYTHON clean_dirk.py
    OUT="DIRK/dirk_all.json"
    ;;
  PLUS)
    if ! $PYTHON -m playwright install chromium >/dev/null 2>&1; then true; fi
    cd PLUS
    run_step $PYTHON main.py
    run_step $PYTHON remove_pattern.py
    run_step $PYTHON fix.py
    run_step $PYTHON clean_plus.py
    OUT="PLUS/structured_plus.json"
    ;;
  LIDL)
    if ! $PYTHON -m playwright install chromium >/dev/null 2>&1; then true; fi
    cd LIDL
    run_step $PYTHON main.py
    run_step $PYTHON structure.py
    run_step $PYTHON clean_lidl.py
    OUT="LIDL/lidl_structured.json"
    ;;
  COOP)
    if ! $PYTHON -m playwright install chromium >/dev/null 2>&1; then true; fi
    cd COOP
    run_step $PYTHON main.py
    run_step $PYTHON structure.py
    run_step $PYTHON clean_coop.py
    OUT="COOP/coop_structured.json"
    ;;
  JUMBO)
    if ! $PYTHON -m playwright install chromium >/dev/null 2>&1; then true; fi
    cd JUMBO
    run_step $PYTHON main.py
    run_step $PYTHON merge.py
    run_step $PYTHON structure.py
    run_step $PYTHON clean_jumbo.py
    OUT="JUMBO/jumbo_structured.json"
    ;;
  *)
    echo "Unknown store: $STORE" >&2
    exit 2
    ;;
esac

cd "$ROOT"
run_step $PYTHON scripts/sanitize_all_stores.py
run_step $PYTHON scripts/validate_products.py
run_step $PYTHON scripts/validate_store_output.py
run_step $PYTHON scripts/prune_stale_artifacts.py

END=$(date +%s)
DURATION=$((END - START))

if [[ -f "$ROOT/$OUT" ]]; then
  COUNT=$($PYTHON -c "import json; print(len(json.load(open('$ROOT/$OUT'))))")
else
  COUNT=0
fi

echo "RESULT=PASS STORE=${STORE} DURATION=${DURATION}s PRODUCTS=${COUNT} OUTPUT=${OUT}" | tee -a "$LOG_FILE"
echo "PASS ${STORE} ${DURATION}s ${COUNT} products"
