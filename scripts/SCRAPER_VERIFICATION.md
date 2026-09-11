# UK scraper refresh verification

Tesco searches use the visible search form in one warmed tab, not repeated
direct navigation to result URLs. On September 11, the direct-navigation flow
returned 36 products then HTTP 403 on Ubuntu/Chrome, including with tab reuse;
the normal form flow passed the same six initial queries. This difference was
not reproducible on native macOS, so macOS-only smoke tests were insufficient.
Each form submission waits for the requested query URL and results heading.
Consent is settled on the homepage, not by reloading a search results page.
If the form times out, the scraper makes one recovery through the homepage
using the same browser context and cookies, then retries that query. It does
not retry an explicit block page, and a second timeout remains a failure.

Use a disposable checkout, never the working directory containing data you want
to keep. `verify_tesco_refresh.py` runs the same `run_store_pipeline.py` used by
the daily workflow, then sanitizes and validates the new Tesco catalog.

It requires all 80 searches, a `refreshed` status (not preserved last-good data),
no blocked/failed/unclassified-empty queries, and passing count and health gates.
A genuine retailer “no results” response is allowed. It never lowers thresholds
or changes timestamps on restored data.

## Linux test runtime

Build from a small context containing just the requirements and Dockerfile:

```sh
task_build=$(mktemp -d)
cp requirements.txt "$task_build/requirements.txt"
cp scripts/Dockerfile.scraper-check "$task_build/Dockerfile"
docker build --platform linux/amd64 -t compears-scraper-check "$task_build"
```

Export a disposable copy of the revision being tested (commit local fixes first
or copy the modified source files into the export before testing):

```sh
task_checkout=$(mktemp -d)
git archive HEAD | tar -x -C "$task_checkout"
docker run --rm --platform linux/amd64 --shm-size=1g \
  -v "$task_checkout:/workspace" compears-scraper-check
```

The container uses Ubuntu 24.04, amd64, Python 3.12.8, locked Playwright and
headed Chrome under Xvfb, matching the daily job's configuration. Network/IP
reputation and runner resources still differ from GitHub, so a local pass is
not a guarantee of live GitHub success. Chrome is installed from its current
stable channel, just as in the daily job.

Results stay in the disposable checkout:

- `artifacts/tesco-status.json`: refreshed versus preserved outcome.
- `artifacts/search-diagnostics/tesco-search.json`: per-query HTTP statuses,
  result counts, extraction method, failure classification and expected-location
  match. Failed operations are recorded as allowlisted stage names, never raw
  exception messages. Query indexes correspond to `countries/uk/_shared/seed_queries.py`.
- `artifacts/tesco-health.json`: cleaned catalog's count, coverage and freshness.

The daily workflow also uploads `search-diagnostics-uk-<store>` artifacts, even
if scraping fails. Diagnostics deliberately exclude raw HTML, body text, page
titles, URLs, cookies, headers and exception messages. Title/body signals are
classified in memory, not saved. Postcodes must not appear in scraper logs.

## Failure interpretation

`blocked` covers HTTP 401/403/429 or recognizable blocking-page text;
`server_error` covers 5xx; `http_error` covers other 4xx. `no_results` requires
explicit empty-search text. `unclassified_empty` means a successful-looking page
yielded nothing and needs investigation; it is not assumed to be a valid empty
catalog. `query_error` records an exception type without its potentially
sensitive message. Use HTTP status, location match and query index together.

Run regression tests with `python -m unittest discover -s tests -t . -v`.
The `Verify Tesco full refresh` workflow runs the same full-run verifier on
relevant pull requests, or on manual dispatch. It has read-only repository
permissions, does not commit catalogs, and never triggers backend seeding.
After merging, GitHub's CodeQL scan must run to resolve the existing postcode
logging alerts; local regression tests do not replace CodeQL analysis.

## Local verification on 2026-09-11

The final Ubuntu 24.04 / Python 3.12.8 / headed Chrome run completed all 80
queries with no unrecovered query errors. It collected 2,134 raw products,
structured 2,126, and retained 2,111 after sanitization. The homepage recovery
path was exercised successfully during the run.

Count and health gates passed: no stale observations, invalid prices, duplicate
identities or contract errors; quantity coverage was 94.5%. Missing product
images remain a non-blocking health warning. All 105 regression tests passed
in the Linux runtime.

Publication replay uses artifacts from daily run `34552672989`, replacing only
Tesco's catalog **and its scrape-status metadata** with the verified local
output. Do not reuse the old status: sanitization uses its observation time.

## Lidl UK extraction

A separate Lidl UK issue was discovered beyond the original Tesco failure:
154 generated products became 106 after quarantining 48 rows, exceeding the
20% catalog-drop gate against the committed 154-product baseline. Generic link
text included accessibility price suffixes, while nearby prices could be a
saving, previous price, unit price, or multi-buy total. Food-word matches also
admitted non-food products such as water-repellent trousers.

The Lidl-specific parser reads each tile's `data-gridbox-impression` metadata:

- Require Lidl's explicit `Food` category, a numeric price, and matching product
  ID/canonical Lidl URL. Unknown categories and malformed tiles fail closed.
- Use the retailer's name, brand and price; remove URL tracking fragments.
- Preserve trusted retailer food classification through sanitization, so a
  genuine grocery without a known pack size is not mistaken for non-food.
  Existing durable-goods rejection still applies.
- Do not infer pack quantity from a unit-price footer. Products with no public
  price (including some bakery products) are not price-comparable and are omitted.
- Mark Lidl Plus prices as loyalty offers. For a multi-buy total, use the
  explicitly displayed single-item regular price; omit it if that is absent.
- Preserve future availability as `preorder` with the retailer's availability
  text, rather than marking it currently in stock.

The daily budget remains 80 searches: the 71 shared food searches plus nine
missing grocery departments, replacing household queries that mostly surface
non-food recommendations. Other retailers keep their existing queries.
The count, drop, growth, freshness and quantity thresholds are unchanged.

To run Lidl in the disposable Linux checkout with the daily runtime (headless
Chromium rather than Tesco's headed Chrome):

```sh
docker run --rm --platform linux/amd64 --shm-size=1g \
  -e PLAYWRIGHT_HEADED=0 -e PLAYWRIGHT_CHANNEL= \
  -v "$task_checkout:/workspace" compears-scraper-check \
  python scripts/run_store_pipeline.py --country uk --store lidl-uk \
  --status-file artifacts/lidl-status.json
```

Replay publication with both new catalogs and their real scrape-status files.
Use `scripts/replay_publish_pipeline.py` in a separate disposable git checkout;
it runs the same ten gates as the publish job and does not push or seed anything.

### Final Lidl and publication results (2026-09-11)

The headless Chromium run completed all 80 searches: 192 raw products, 190
structured products and 190 after publication sanitization. No HTTP-blocked
searches occurred. The plain bread search redirected to an unpriced bakery page
and contributed no offers; the final redirect guard is covered by regression
tests. One slow navigation recovered through the existing bounded navigation
helper. No rejected or duplicate rows remained in Lidl's final catalog.

Lidl's health result was **pass**, with zero invalid prices, stale observations,
or contract errors. Quantity coverage was 39.5%, brand coverage 68.9%, and product
URL/image coverage 100%. The catalog-drop check passed against the unchanged
154-product baseline (new count 190).

The final Ubuntu 24.04 / Python 3.12.8 publication replay passed **all ten gates**,
including 118 regression tests, freshness/drop monitoring, comparison index,
and publish manifest: 79,404 cleaned offers across 18 stores, with all 14 required
stores fresh and usable. The four optional stores (Coop, REWE, Penny and Asda)
still used their previously preserved catalogs and produced existing warnings;
their underlying source-access problems are not repaired by this change.

These are local verification results, not a production publication. GitHub CI,
the live Tesco verification, and CodeQL must run on the PR; the two existing
postcode-logging alerts can close after the fixed code is scanned on main.
