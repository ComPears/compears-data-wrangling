"""Shared Playwright helpers for resilient scraping in CI."""

from __future__ import annotations

import sys
import time
from typing import Callable

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/44.0.4919.1885 Safari/537.36"
)


def configure_page(page: Page, width: int = 1600, height: int = 900) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.set_extra_http_headers({"User-Agent": DEFAULT_USER_AGENT})


def goto_resilient(
    page: Page,
    url: str,
    *,
    timeout: int = 60000,
    retries: int = 3,
    retry_delay: float = 5.0,
) -> None:
    """Navigate with retries and progressively looser wait conditions."""
    wait_strategies = ("domcontentloaded", "load")
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        for wait_until in wait_strategies:
            try:
                page.goto(url, wait_until=wait_until, timeout=timeout)
                return
            except PlaywrightTimeoutError as err:
                last_error = err
                print(
                    f"⚠️ Timeout navigating to {url} ({wait_until}), "
                    "trying next strategy..."
                )
            except Exception as err:
                last_error = err
                print(
                    f"⚠️ {type(err).__name__} navigating to {url} "
                    f"({wait_until}): {err}"
                )

        if attempt < retries:
            delay = retry_delay * attempt
            print(f"🔁 Retry {attempt}/{retries - 1} for {url} in {delay:.0f}s...")
            time.sleep(delay)

    raise RuntimeError(
        f"Failed to navigate to {url} after {retries} attempts"
    ) from last_error


def wait_for_products(page: Page, selector: str, timeout: int = 15000) -> None:
    """Wait for product cards to appear after pagination or lazy loading."""
    try:
        page.wait_for_selector(selector, timeout=timeout)
    except PlaywrightTimeoutError:
        page.wait_for_timeout(3000)


def run_url_batch(
    urls: list[str],
    scrape_fn: Callable[[str], None],
    *,
    max_failure_ratio: float = 0.5,
) -> None:
    """Run a scrape function per URL; exit non-zero if too many fail."""
    if not urls:
        return

    failures: list[tuple[str, str]] = []

    for url in urls:
        try:
            scrape_fn(url)
        except Exception as err:
            msg = f"{type(err).__name__}: {err}"
            print(f"❌ Failed to scrape {url}: {msg}")
            failures.append((url, msg))

    if not failures:
        return

    print(f"⚠️ {len(failures)}/{len(urls)} URLs failed:")
    for url, msg in failures:
        print(f"   - {url}: {msg}")

    failure_ratio = len(failures) / len(urls)
    if failure_ratio > max_failure_ratio:
        print(
            f"❌ Failure rate {failure_ratio:.0%} exceeds limit "
            f"{max_failure_ratio:.0%}"
        )
        sys.exit(1)
