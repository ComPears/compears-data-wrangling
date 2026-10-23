# Security maintenance: 23 October 2026

## Findings and fixes

- Upgrade Playwright to 1.64.0 (Dependabot #56), Python from 3.12.8 to 3.12.15,
  and the local verification image's uv from 0.8.22 to 0.13.4.
- Playwright Python bundles Node separately. Explicitly use Node 22.23.4 via
  PLAYWRIGHT_NODEJS_PATH rather than assuming the wheel contains the Brotli fix.
  Runtime verification inspects the executable Playwright will actually use and
  rejects vulnerable or unsupported Node versions.
- Bootstrap pip 26.2.2 using the official hash-pinned wheel before resolving any
  other dependencies. Pin certifi 2026.10.19. Updating certifi alone does not fix
  pip's independently vendored CA store. Do not reuse old virtualenvs unmodified.
- Bootstrap and CI pip use legacy-certs mode with the patched vendored bundle,
  avoiding a union with a potentially stale system trust store. The four urllib
  clients use an explicit certifi SSL context, with hostname/certificate checks
  enabled. They do not fall back to the host's old roots.
- All Python workflows share one setup action. The verification image pulls
  current OS CA packages and uses patched Node/uv/pip. Rebuild it with --pull and
  --no-cache. CI audits the installed Python environment using pinned pip-audit.
- Ubuntu's system Brotli package is still awaiting vendor evaluation. The test
  image builds upstream Brotli 1.1.1 from a checksum-pinned source archive and
  puts its shared libraries first in the dynamic loader path. A build assertion
  checks the effective decoder version. Keep this temporary backport until the
  distro ships its fix; OS package inventory still records Ubuntu's original
  package. Both the image and disposable Ubuntu CI runners explicitly disable
  the affected emSign G3 OS root, including for Git/curl clients using system trust.
- Dependabot #55's action versions already match main. GitHub reported no open
  Dependabot or CodeQL alerts at review time; package/runtime checks were still needed.

## Verification

On Python 3.12.15 / Node 22.23.4: 201 regression tests, pip check, pip-audit and
catalog validation pass. A real upgraded Chromium/Playwright local-page smoke
test passes. Tests verify the affected emSign G3 root is absent from the scraper
SSL context, TLS verification stays enabled, and old Node versions are rejected.
The amd64 Ubuntu image builds with --pull --no-cache; all 201 tests and runtime
verification also pass inside it, using a disposable copy of the source.
No live catalog refresh/publication was triggered. Existing ALDI NL/UK quantity
coverage warnings remain data-quality concerns, not dependency failures.

## Rollout and limits

Merge and rerun workflows so new runners use this setup. Rebuild local Docker
images and virtualenvs; don't reuse cached CA bundles. The amd64 headed-Chrome
Docker workflow requires an amd64 host or working emulation. Browser trust
stores and GitHub action-internal Node are
managed separately; keep hosted runners and Chrome current. Custom corporate CA
requirements should be reviewed explicitly, never worked around with disabled TLS.
These changes do not prove the absence of malware or patch existing hosts globally.

Sources: [Python security announcement](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576),
[Node security release](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases),
[Playwright custom Node support](https://playwright.dev/python/docs/browsers#using-a-pre-installed-nodejs),
[Ubuntu CVE status](https://ubuntu.com/security/CVE-2026-111497),
[Brotli 1.1.1](https://github.com/google/brotli/releases/tag/v1.1.1).
