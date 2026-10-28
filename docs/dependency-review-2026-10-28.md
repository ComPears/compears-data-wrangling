# Dependency review: 28 October 2026

## Changes

- Incorporates Dependabot #58 (Playwright 1.64.1) and #55 (GitHub Actions updates).
- Update SHA-pinned setup-node in the shared secure-runtime action, plus
  upload/download-artifact and CodeQL in every affected workflow.
- Preserve Python 3.12.15, the patched Node 22.23.4 Playwright override, pip
  26.2.2, certifi 2026.10.19 and the existing CA/Brotli security controls.
- GitHub returned no open Dependabot vulnerability or CodeQL alerts at review
  time. Open version-update PRs are distinct from vulnerability alerts.

## Local verification

Using a disposable source copy in the existing patched amd64 Linux verification
image, install the updated requirements and run:

- `python scripts/verify_secure_runtime.py`: passes.
- `python -m pip check`: no broken requirements.
- `python -m unittest discover -s tests -t . -q -b`: all 201 tests pass.
- `python -m pip_audit`: no known vulnerabilities.
- Real Playwright 1.64.1 / Chrome 156.0.8078.47 headless local-page interaction
  smoke test passes without contacting retailer sites.
- All workflows pass actionlint; `git diff --check` passes.

## Rollout and limits

Merge after reviewing CI and CodeQL. Rebuild local verification images so their
installed Playwright matches the new pin. The test used the existing patched
image with freshly installed requirements, not a new image build. No live
retailer refresh or catalog publication was manually triggered during local
validation. PR-triggered PLUS/Tesco checks provide separate live-site evidence;
dependency tests cannot guarantee retailer availability. Dependency audits are
not a comprehensive malware assessment.
