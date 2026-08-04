# Germany store scrapers

Playwright search scrapers for Edeka (via EDEKA24), REWE, Lidl DE, Aldi Süd, and Penny. Shared helpers live in `_shared/` (mirrors the UK pattern).

## Prerequisites

```bash
cd compears-data-wrangling
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Run one store (full seed list, default `DE_MAX_QUERIES=80`)

```bash
python scripts/run_store_pipeline.py --country de --store edeka --soft-fail
python scripts/run_store_pipeline.py --country de --store rewe --soft-fail
python scripts/run_store_pipeline.py --country de --store lidl-de --soft-fail
python scripts/run_store_pipeline.py --country de --store aldi-sud --soft-fail
python scripts/run_store_pipeline.py --country de --store penny --soft-fail
```

## Smoke test (few queries)

```bash
DE_MAX_QUERIES=3 python scripts/run_store_pipeline.py --country de --store lidl-de --soft-fail
```

Useful env knobs:

- `DE_MAX_QUERIES` — cap seed queries (default 80)
- `DE_MAX_EMPTY_QUERIES` — stop after N consecutive empty queries (default 5)
- `DE_MAX_BLOCKED_QUERIES` — stop after N consecutive 401/403 API responses (default 3)

Stores are marked `optional: true` in `config/stores.json` because German sites often use cookie/bot walls and PLZ/market gates. `run_store_pipeline.py --soft-fail` restores the last-good structured catalog when a scrape under-delivers.
