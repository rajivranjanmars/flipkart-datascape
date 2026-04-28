"""Utility helpers for Flipkart scraping with a shared Playwright runtime."""

from __future__ import annotations

import atexit
import random
import time
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

USER_AGENTS: list[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.6167.160 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) "
        "Gecko/20100101 Firefox/123.0"
    ),
    (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) "
        "Gecko/20100101 Firefox/122.0"
    ),
]

_PLAYWRIGHT_MANAGER: Any | None = None
_PLAYWRIGHT_USER_AGENT = USER_AGENTS[0]


def _get_playwright_manager() -> Any:
    """Start the shared Playwright manager once and reuse it across contexts."""

    global _PLAYWRIGHT_MANAGER

    if _PLAYWRIGHT_MANAGER is None:
        _PLAYWRIGHT_MANAGER = sync_playwright().start()

    return _PLAYWRIGHT_MANAGER


def _shutdown_playwright_manager() -> None:
    """Stop the shared Playwright manager during process teardown."""

    global _PLAYWRIGHT_MANAGER

    if _PLAYWRIGHT_MANAGER is None:
        return

    try:
        _PLAYWRIGHT_MANAGER.stop()
    except Exception:
        pass
    finally:
        _PLAYWRIGHT_MANAGER = None


atexit.register(_shutdown_playwright_manager)


def get_headers() -> dict[str, str]:
    """Return randomized browser-like headers for Flipkart requests."""

    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.flipkart.com",
    }


def create_browser_context() -> tuple[Browser, BrowserContext]:
    """Launch Chromium and return a primed browser/context pair for scraping."""

    playwright_manager = _get_playwright_manager()
    browser: Browser = playwright_manager.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context: BrowserContext = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="en-IN",
        user_agent=_PLAYWRIGHT_USER_AGENT,
    )
    context.set_extra_http_headers(
        {
            "Accept-Language": "en-IN",
            "Referer": "https://www.flipkart.com",
        },
    )

    page: Page | None = None

    try:
        page = context.new_page()
        page.goto(
            "https://www.flipkart.com",
            timeout=30000,
            wait_until="domcontentloaded",
        )
        time.sleep(2)
    except Exception:
        context.close()
        browser.close()
        raise
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass

    return browser, context


def get_page_html(
    context: BrowserContext,
    url: str,
    wait_seconds: float = 2.5,
) -> str | None:
    """Return HTML for a URL using a shared browser context and per-page jitter."""

    page: Page | None = None

    try:
        page = context.new_page()
        page.goto(
            url,
            timeout=30000,
            wait_until="domcontentloaded",
        )
        time.sleep(wait_seconds + random.uniform(0.5, 1.5))
        return page.content()
    except Exception as exc:
        print(f"Warning: failed to load page HTML for {url}: {exc}")
        return None
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
