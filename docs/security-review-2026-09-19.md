# Security review — 19 September 2026

## Artifact trust-boundary hardening

The publish job previously merged scraper artifacts directly into the repository root and then executed repository scripts with a write-capable GitHub token. A malformed or compromised scraper artifact could overwrite those scripts or other repository files. This was not a demonstrated external exploit: the workflow is scheduled/manually dispatched, not triggered by untrusted pull requests.

Artifacts now download into a separate runner temporary directory. A shared importer accepts only the configured catalog and scrape-status JSON for each store, rejects extra files and symlinks, checks containment, file sizes and JSON shapes, and validates the entire batch before copying any files. Local publish replay uses the same importer. No executable artifact content is copied into the workspace. Existing product-contract and freshness gates still run after import.

Publishing to main is restricted to main-branch runs. Manual runs on other branches can still exercise scrapers but cannot publish or trigger backend synchronization. The scraper checkout no longer persists a GitHub credential.

Seven new tests cover a complete batch across all 18 stores, attempted script injection, incomplete batches, malformed JSON, source/destination symlinks, and oversized files. All 131 regression tests passed locally. No live scrape, catalog publication, or backend seed was triggered during this review.

## Dependency and malware checks

- GitHub reported no open Dependabot PRs, vulnerability alerts, CodeQL findings, or secret-scanning alerts.
- Resolved the complete requirements tree with `uv pip compile`: Playwright 1.62.0, greenlet 3.5.6, pyee 13.0.1 and typing-extensions 4.16.0.
- `pip-audit --no-deps --disable-pip` against that fully resolved four-package list reported no known vulnerabilities. The normal pip-audit resolver hit a local ensurepip crash, so dependency resolution and advisory querying were run separately. This does not audit Playwright's downloaded browser binaries.
- Reviewed tracked Python/shell/workflow code for dynamic execution, suspicious encoded payload execution, and shell download/execute patterns. Common private-key/token pattern checks and GitHub's open secret-alert query found no matches.

No malware indicators were identified within these checks. This is not an exhaustive malware clearance, dependency source audit, host audit, or git-history secret scan. Keep Dependabot and CodeQL enabled; require successful PR checks and review before merging. No branch protection, token scopes, secrets, or production settings were changed.
