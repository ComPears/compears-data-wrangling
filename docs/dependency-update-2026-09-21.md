# Dependabot consolidation — 21 September 2026

Includes #46 (Playwright 1.62.0 → 1.63.0) and #47 (the updated, commit-pinned CodeQL action).

Verification: all 131 regression tests pass under Python 3.12 with Playwright 1.63.0 installed. `uv pip check` reports compatible installed dependencies. The complete resolved requirements tree (Playwright 1.63.0, greenlet 3.5.6, pyee 13.0.1, typing-extensions 4.16.0) has no known vulnerabilities in `pip-audit`. Workflow YAML parses successfully.

The Render heap failure is addressed in the backend and frontend companion PRs. No catalogs were reduced or modified here. The backend seed pipeline now checks the memory cost of the newly seeded NL/UK/DE snapshot before publication and deployment. Live retailer scraping and production pipeline dispatch are not part of this dependency test; scheduled scraper jobs continue to install the browser version matching the pinned Playwright package.

These changes incorporate the open Dependabot PRs into a tested branch; they do not merge or close those PRs or deploy production.
