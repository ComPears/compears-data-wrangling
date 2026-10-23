#!/usr/bin/env bash
# Run inside a virtualenv (or the disposable setup-python CI environment).
set -euo pipefail
PYTHON="${PYTHON:-python}"
# Python security team's hash-pinned bootstrap: do not trust an old pip CA bundle
# to select/download an unpinned installer during the emSign incident.
# Ubuntu's old bootstrap pip does not recognize legacy-certs yet.
env -u PIP_USE_DEPRECATED "$PYTHON" -m pip install --no-cache-dir --upgrade --no-deps 'pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70'
# Avoid unioning a potentially stale system trust store with pip's patched bundle.
export PIP_USE_DEPRECATED=legacy-certs
"$PYTHON" -m pip install --no-cache-dir -r "$(dirname "$0")/../requirements.txt"
"$PYTHON" -m pip check
