"""Explicit, patched trust store for scraper HTTP clients (not the host CA union)."""
from functools import lru_cache
import ssl

import certifi


@lru_cache(maxsize=1)
def scraper_ssl_context() -> ssl.SSLContext:
    # Passing cafile explicitly avoids loading compromised roots from an old OS
    # trust store. Keep hostname/certificate verification enabled.
    return ssl.create_default_context(cafile=certifi.where())
