# Daily catalog recovery — 2026-09-27

## Incident

The last successful daily publication was September 21. Scheduled runs on
September 22–26 included a PLUS job cancelled at GitHub's two-hour deadline.
Publication also failed independently:

- September 22: Jumbo's artifact upload failed; the importer rejected the missing artifact.
- September 23: PLUS's retained observations failed the catalog health gate.
- September 24–27: Lidl UK package-size coverage fell below its unchanged 18% floor.
  Run 36288335083 produced 175 Lidl products, only 10 with quantities (5.71%).
- Replaying past the quantity gate revealed another real failure: 175 products
  versus the previous 241 exceeded the unchanged 20% count-drop limit.

The 131 original unit tests passed. Negative tests printed GitHub workflow
commands, creating misleading Tesco/PLUS error annotations despite passing.

## Changes

- Lidl UK visits a bounded number of missing-size product pages (250 requests,
  300-second scheduling budget, eight-second request timeout, 2 MiB response cap).
  Only explicit short-description quantities with a matching article number are
  accepted. Redirects are rejected; requests are restricted to Lidl UK product
  URLs. Unit prices, nutrition text and ambiguous variant sizes are not quantities.
  The source URL and quantity observation timestamp remain in the data.
- Add 20 broad grocery department queries to the existing 80 Lidl searches.
  Consume up to the retailer's 48 tiles per page rather than the shared cap of 36.
  Other UK stores retain their existing query budgets. Food classification and
  price/identity validation remain mandatory.
- Disable optional PLUS barcode enrichment in the daily workflow. The previous
  configuration attempted up to 1,500 detail lookups; the September 27 run added
  zero barcodes. Explicit opt-in local barcode enrichment remains available.
- Give store subprocesses a shared 60-minute budget, inside the two-hour job.
  On expiry, terminate the process group, restore the original catalog and write
  a `preserved` status with its original successful observation timestamp. This
  leaves time for artifact upload and does not make stale catalogs fresh.
- A wholly missing artifact may use the repository snapshot only if its counts,
  contract, quantities, health and observation ages pass validation. A missing,
  corrupt, stale or future-dated fallback fails closed. Present but malformed,
  oversized, symlinked or unexpected artifact contents still abort the import
  before any planned files are written.
- Buffer successful unit-test output in CI, publication and local replay. Failed
  tests still show captured output. Health failures now print their actual issue
  codes and thresholds alongside the summary table.

No count, freshness or quantity thresholds have been relaxed. No store has been
made optional. Historical catalog files and stored baseline reports are not
changed in this PR.

## Verification

- 150 local regression tests pass, including real subprocess-group timeout and
  rollback tests, artifact fallback safety, identity checks, quantity parsing and
  preservation of price-observation timestamps through quantity enrichment.
- `pip check`, Python compilation, committed-catalog validation and workflow YAML
  parsing pass.
- Downloaded all 18 catalog artifacts and Lidl raw observations from run
  36288335083 into a disposable checkout. Reproduced the quantity failure after
  the same sanitization step used by GitHub.
- Ran bounded live product-detail enrichment over those observations: 166 unique
  requests, 140 enriched raw rows. After structuring and sanitizing, 149/175
  products (85.14%) have valid quantities; the original 18% floor passes.
- The first complete publication replay correctly stopped at the newly exposed
  count-drop gate. A live scrape of all 20 added grocery queries returned 145
  products, including 33 additional unique products beyond the failed-run data.
  Combining those real observations with the enriched failed-run observations
  produced 208 products; all 208 survived sanitization, and 179 (86.06%) have
  quantities. No prices or quantities were invented to meet the gates.
- Replayed all ten publication steps in a disposable checkout using all 18
  failed-run artifacts with the recovered Lidl catalog substituted. Every gate
  passed, including the unchanged count-drop check; the manifest reports 14/14
  required stores OK, 79,393 products, 14 refreshed and four preserved stores.
  This is an artifact replay with live Lidl recovery, not a new full-country run.
- An independent, complete live Lidl run then finished all 100 queries and all
  pipeline stages within a stricter local 20-minute budget: 213 raw products,
  199 detail requests, 165 enriched rows, and 208 structured products. Its final
  quantity coverage is 174/208 (83.65%), comfortably above the unchanged 18% floor.
- PLUS live smoke testing retrieved 4,597 products across its first seven
  categories with optional barcode enrichment disabled. The temporary test was
  deliberately stopped before completing the full catalog; the wrapper restored
  the disposable baseline. Full PLUS completion within the new production
  budget remains to be confirmed by a post-merge run. Timeout/process cleanup and
  honest rollback statuses are covered by passing regression tests.

## Rollout

After review and merge, dispatch `Daily supermarket scrapers` on `main` and check
the publish manifest plus backend seed. Do not rerun just the old failed publish
job: it still uses the old workflow revision and old incomplete artifacts.
Branch runs cannot publish to main. No production scrape, seed or deployment is
triggered as part of preparing this PR.

The optional Coop, Rewe, Penny and Asda source failures remain separate warnings;
their old observations must not be relabelled as fresh.
