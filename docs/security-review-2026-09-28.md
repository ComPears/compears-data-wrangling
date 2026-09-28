# Dependency and security review — 2026-09-28

## Open PR covered

Includes #51's CodeQL update to the pinned revision
`2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2`. The bot PR should only be closed after
this replacement is merged. The previous recovery/timestamp PRs are already on
main; their quality gates are unchanged.

## Finding and fix

**Status artifacts were interpolated directly into Actions warnings and Markdown
summaries.** Newlines in status text could manufacture additional workflow
annotations; Markdown/HTML could change the displayed summary. This is a
log/report-integrity issue, not evidence of remote code execution.

The summary now escapes percent, CR and LF in annotation messages and treats
table cells as escaped single-line text. Non-object status JSON is skipped with
a bounded warning instead of crashing the summary. Regression tests exercise
forged `::error::` commands, links, HTML and injected table rows.

The existing artifact importer rejects executable/unexpected files, symlinks,
oversized JSON and invalid shapes before any writes. Missing-artifact fallback
still requires a fresh, valid snapshot. No freshness, quantity or count gates
were relaxed, and no production scrape or seed was manually triggered.

## Verification

- GitHub: zero open Dependabot, CodeQL and secret-scanning alerts at review time.
- All 153 Python regression tests pass, including the new summary boundary tests.
- `pip check`, workflow YAML parsing and committed-catalog validation pass.
  Existing nonblocking quantity-coverage warnings remain visible.
- Resolved application requirements in a temporary directory and audited that
  directory with pip-audit 2.10.1: no known vulnerabilities in Playwright 1.63.0,
  greenlet 3.5.6, pyee 13.0.1 or typing-extensions 4.16.0. The audit tool and its
  own dependencies were kept outside the repository/application environment.
- The audit tool's initial nested-venv resolution failed locally; the successful
  audit used its supported `--path` mode after pip resolved requirements.txt.

The Python direct requirement is pinned, but its transitive versions remain
resolver-controlled; the versions above identify this review's snapshot. Scans
cannot guarantee the absence of malware or unknown vulnerabilities. This review
does not claim to cover every retailer response or production host.
