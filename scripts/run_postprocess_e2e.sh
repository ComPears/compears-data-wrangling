#!/usr/bin/env bash
# Mirror the CI post-scrape pipeline on committed catalogs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
LOG_DIR="${ROOT}/.local-test-logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/postprocess-e2e.log"
START=$(date +%s)

run_step() {
  echo "=== $* ===" | tee -a "$LOG_FILE"
  "$@" >>"$LOG_FILE" 2>&1
}

{
  echo "START=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "ROOT=${ROOT}"
} >"$LOG_FILE"

cd "$ROOT"
run_step "$PYTHON" scripts/sanitize_all_stores.py
run_step "$PYTHON" scripts/validate_store_output.py
run_step "$PYTHON" scripts/validate_products.py
run_step "$PYTHON" -m unittest discover -s tests -t . -v
run_step "$PYTHON" scripts/catalog_health.py --fail-on error
run_step "$PYTHON" scripts/prune_stale_artifacts.py

END=$(date +%s)
DURATION=$((END - START))
echo "RESULT=PASS DURATION=${DURATION}s" | tee -a "$LOG_FILE"
echo "PASS postprocess-e2e ${DURATION}s"
