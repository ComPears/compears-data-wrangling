"""Shared Playwright helpers for resilient scraping in CI."""

from __future__ import annotations

import sys
import time
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import Browser, Page, Playwright, TimeoutError as PlaywrightTimeoutError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class EmptyCategoryError(RuntimeError):
    """Raised when a category URL loads but yields no product cards."""


def launch_browser(playwright: Playwright, *, browser: str = "chromium") -> Browser:
    """Launch a headless browser; Chromium is more stable than Firefox in CI."""
    launcher = getattr(playwright, browser)
    return launcher.launch(headless=True)


def strip_pagination_param(url: str) -> str:
    """Remove ?page=N so scrapers always start from the first page."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query.pop("page", None)
    flat = {key: values[0] for key, values in query.items()}
    return urlunparse(parsed._replace(query=urlencode(flat)))


def configure_page(page: Page, width: int = 1600, height: int = 900) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.set_extra_http_headers({"User-Agent": DEFAULT_USER_AGENT})


def click_button_if_visible(page: Page, selector: str, *, timeout: int = 3000) -> bool:
    """Click a button if it exists and is visible (e.g. cookie consent)."""
    try:
        button = page.locator(selector).first
        if button.is_visible(timeout=timeout):
            button.click()
            page.wait_for_timeout(1000)
            return True
    except Exception:
        pass
    return False


def click_pagination_if_ready(
    page: Page,
    selector: str,
    *,
    click_timeout: int = 15000,
    label: str = "pagination",
) -> bool:
    """Click a pagination button when ready; return False instead of raising."""
    try:
        button = page.locator(selector).first
        if not button.count():
            return False
        if not button.is_visible(timeout=3000):
            return False
        if not button.is_enabled():
            return False
        button.scroll_into_view_if_needed()
        button.click(timeout=click_timeout)
        page.wait_for_timeout(1500)
        return True
    except PlaywrightTimeoutError:
        print(f"⚠️ {label} click timed out; keeping products collected so far")
        return False
    except Exception as err:
        print(f"⚠️ {label} click failed ({type(err).__name__}: {err})")
        return False


def accept_common_cookies(page: Page) -> None:
    """Try common Dutch cookie-consent button labels."""
    for selector in (
        "button:has-text('Accepteren')",
        "button:has-text('Alles accepteren')",
        "button:has-text('Akkoord')",
        "button:has-text('Accepteer')",
        "button:has-text('Alle cookies accepteren')",
    ):
        if click_button_if_visible(page, selector):
            print(f"🍪 Accepted cookies via {selector}")
            return


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


def require_products(count: int, label: str, *, min_count: int = 1) -> None:
    """Fail a category scrape when no products were collected."""
    if count < min_count:
        raise EmptyCategoryError(
            f"No products scraped for {label} (got {count}, need >= {min_count})"
        )


def report_batch_failures(
    failures: list[tuple[str, str]],
    total: int,
    *,
    max_failure_ratio: float = 0.5,
    label: str = "URLs",
) -> None:
    """Print failures and exit non-zero if too many categories failed."""
    if not failures:
        return

    print(f"⚠️ {len(failures)}/{total} {label} failed:")
    for url, msg in failures:
        print(f"   - {url}: {msg}")

    failure_ratio = len(failures) / total
    if failure_ratio > max_failure_ratio:
        print(
            f"❌ Failure rate {failure_ratio:.0%} exceeds limit "
            f"{max_failure_ratio:.0%}"
        )
        sys.exit(1)


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

    report_batch_failures(failures, len(urls), max_failure_ratio=max_failure_ratio)
