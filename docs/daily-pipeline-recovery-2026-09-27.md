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

- 149 local regression tests pass, including real subprocess-group timeout and
  rollback tests, artifact fallback safety, identity checks and quantity parsing.
- `pip check`, Python compilation, committed-catalog validation and workflow YAML
  parsing pass.
- Downloaded all 18 catalog artifacts and Lidl raw observations from run
  36288335083 into a disposable checkout. Reproduced the quantity failure after
  the same sanitization step used by GitHub.
- Ran bounded live product-detail enrichment over those observations: 166 unique
  requests, 140 enriched raw rows. After structuring and sanitizing, 149/175
  products (85.14%) have valid quantities; the original 18% floor passes.
- The first complete publication replay correctly stopped at the newly exposed
  count-drop gate. Broad-department live verification and the final replay are
  recorded below once complete.

## Rollout

After review and merge, dispatch `Daily supermarket scrapers` on `main` and check
the publish manifest plus backend seed. Do not rerun just the old failed publish
job: it still uses the old workflow revision and old incomplete artifacts.
Branch runs cannot publish to main. No production scrape, seed or deployment is
triggered as part of preparing this PR.

The optional Coop, Rewe, Penny and Asda source failures remain separate warnings;
their old observations must not be relabelled as fresh.
