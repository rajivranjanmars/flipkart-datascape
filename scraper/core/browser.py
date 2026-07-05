"""Fast, site-agnostic Playwright fetch engine.

The two big speed levers over a naive scraper live here:

1. ``block_resources`` aborts images, media, fonts, and stylesheets. Only the
   HTML/JSON we actually parse is downloaded, which slashes bandwidth and load
   time on image-heavy marketplace pages.
2. ``ready_selector`` waits for the real content to appear instead of sleeping a
   fixed number of seconds on every single page. A page that loads in 700ms no
   longer pays a flat 3-6 second tax.

A :class:`BrowserSession` keeps one browser/context alive across many fetches so
batch workers stop relaunching Chromium for every product.
"""

from __future__ import annotations

import atexit
import random
import time
from contextlib import suppress
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Route, sync_playwright

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

USER_AGENTS: list[str] = [
    DEFAULT_USER_AGENT,
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
]

# Resource types that are never needed to parse listing or review content.
_BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font", "stylesheet"})

# Default time to let late client-side hydration settle after the ready signal.
_DEFAULT_SETTLE_MS = 350

# Stealth: hide the headless/automation tells that anti-bot edges fingerprint.
# Without this, Amazon (503) and Meesho (Akamai "Access Denied") reject the
# default HeadlessChrome + navigator.webdriver=true client outright.
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en', 'hi']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
const _q = window.navigator.permissions && window.navigator.permissions.query;
if (_q) {
  window.navigator.permissions.query = (p) =>
    p && p.name === 'notifications'
      ? Promise.resolve({state: Notification.permission})
      : _q(p);
}
"""

# Markers of an anti-bot interstitial / throttle page (paired with a small body).
_BLOCK_MARKERS = (
    "access denied",
    "service unavailable",
    "site maintenance",
    "something went wrong",
    "enter the characters",
    "are you a human",
    "captcha",
    "robot check",
    "rush hour",
    # Amazon's anti-scraping throttle / 503 interstitial:
    "to discuss automated access",
    "automated access to amazon",
    "validatecaptcha",
)

_PLAYWRIGHT_MANAGER: Any | None = None


def _chrome_user_agent(major: str) -> str:
    """A realistic desktop Chrome UA for the given major version."""

    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )


def _stealth_headers(major: str) -> dict[str, str]:
    """Client-hint and fetch-metadata headers a real Chrome sends."""

    return {
        "sec-ch-ua": f'"Chromium";v="{major}", "Not_A Brand";v="24", "Google Chrome";v="{major}"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
    }


def looks_blocked(html: str | None) -> bool:
    """Heuristic: is this an anti-bot interstitial rather than real content?

    Block pages are tiny and carry a known marker; real listing/review pages are
    large, so the size guard keeps false positives away from genuine content.
    """

    if not html:
        return False  # None is handled as a fetch failure elsewhere
    if len(html) > 8000:
        return False
    low = html.lower()
    return any(marker in low for marker in _BLOCK_MARKERS)


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

    with suppress(Exception):
        _PLAYWRIGHT_MANAGER.stop()

    _PLAYWRIGHT_MANAGER = None


atexit.register(_shutdown_playwright_manager)


def _install_resource_blocking(context: BrowserContext) -> None:
    """Abort image/media/font/stylesheet requests for the lifetime of a context."""

    def _handler(route: Route) -> None:
        if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
            with suppress(Exception):
                route.abort()
            return
        with suppress(Exception):
            route.continue_()

    context.route("**/*", _handler)


def create_browser_context(
    *,
    block_resources: bool = True,
    prime_url: str | None = None,
    locale: str = "en-IN",
    user_agent: str | None = None,
    extra_headers: dict[str, str] | None = None,
    prime_settle_seconds: float = 1.5,
    timezone_id: str = "Asia/Kolkata",
    stealth: bool = True,
    cookies: list[dict] | None = None,
    proxy: dict[str, str] | None = None,
) -> tuple[Browser, BrowserContext]:
    """Launch Chromium and return a primed, stealthed browser/context pair.

    The UA and client-hint headers are derived from the *real* browser version so
    they never drift out of sync with the engine (a classic bot tell). Pass an
    explicit ``user_agent`` to override.

    ``proxy`` is a Playwright-shaped dict (``{"server", "username", "password"}``);
    see :func:`scraper.core.proxy.resolve_proxy_from_env` for the usual source.
    """

    manager = _get_playwright_manager()
    browser: Browser = manager.chromium.launch(
        headless=True,
        proxy=proxy,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )

    major = (browser.version or "145").split(".", 1)[0]
    resolved_ua = user_agent or _chrome_user_agent(major)
    headers = _stealth_headers(major) if stealth else {}
    if extra_headers:
        headers.update(extra_headers)

    context: BrowserContext = browser.new_context(
        viewport={"width": 1366, "height": 768},
        locale=locale,
        timezone_id=timezone_id,
        user_agent=resolved_ua,
    )

    if headers:
        context.set_extra_http_headers(headers)

    if stealth:
        context.add_init_script(_STEALTH_JS)

    if cookies:
        try:
            context.add_cookies(cookies)
        except Exception:
            # One malformed cookie shouldn't sink the whole session; add the
            # rest individually and skip the bad ones.
            for cookie in cookies:
                with suppress(Exception):
                    context.add_cookies([cookie])

    if block_resources:
        _install_resource_blocking(context)

    if prime_url:
        page: Page | None = None
        try:
            page = context.new_page()
            page.goto(prime_url, timeout=30000, wait_until="domcontentloaded")
            if prime_settle_seconds > 0:
                time.sleep(prime_settle_seconds)
        except Exception:
            with suppress(Exception):
                context.close()
            with suppress(Exception):
                browser.close()
            raise
        finally:
            if page is not None:
                with suppress(Exception):
                    page.close()

    return browser, context


def fetch_html(
    context: BrowserContext,
    url: str,
    *,
    ready_selector: str | None = None,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30000,
    selector_timeout_ms: int = 12000,
    settle_ms: int = _DEFAULT_SETTLE_MS,
    jitter: bool = False,
) -> str | None:
    """Return HTML for ``url`` using a shared context.

    Instead of sleeping a flat number of seconds, this waits for
    ``ready_selector`` (when provided) and then settles briefly for late
    hydration. Pages that load quickly return quickly.
    """

    page: Page | None = None

    try:
        page = context.new_page()
        page.goto(url, timeout=timeout_ms, wait_until=wait_until)

        if ready_selector:
            with suppress(Exception):
                page.wait_for_selector(
                    ready_selector,
                    timeout=min(timeout_ms, selector_timeout_ms),
                    state="attached",
                )

        settle = settle_ms / 1000.0
        if jitter:
            settle += random.uniform(0.1, 0.5)
        if settle > 0:
            time.sleep(settle)

        return page.content()
    except Exception as exc:  # noqa: BLE001 - network/parse errors are expected
        print(f"Warning: failed to load page HTML for {url}: {exc}")
        return None
    finally:
        if page is not None:
            with suppress(Exception):
                page.close()


class BrowserSession:
    """A reusable browser/context wrapper that survives across many fetches.

    Launching Chromium is the expensive part of scraping. Batch workers should
    create one session and call :meth:`fetch` repeatedly rather than relaunch a
    browser per product.
    """

    def __init__(
        self,
        *,
        block_resources: bool = True,
        prime_url: str | None = None,
        locale: str = "en-IN",
        user_agent: str | None = None,
        extra_headers: dict[str, str] | None = None,
        cookies: list[dict] | None = None,
        proxy: dict[str, str] | None = None,
    ) -> None:
        self._options = {
            "block_resources": block_resources,
            "prime_url": prime_url,
            "locale": locale,
            "user_agent": user_agent,
            "extra_headers": extra_headers,
            "cookies": cookies,
            "proxy": proxy,
        }
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None

    def start(self) -> "BrowserSession":
        """Launch the browser/context if it is not already running."""

        if self.context is None:
            self.browser, self.context = create_browser_context(**self._options)
        return self

    def fetch(self, url: str, **kwargs: Any) -> str | None:
        """Fetch a URL using the long-lived context, starting it on first use."""

        if self.context is None:
            self.start()
        assert self.context is not None
        return fetch_html(self.context, url, **kwargs)

    def close(self) -> None:
        """Tear down the context and browser."""

        if self.context is not None:
            with suppress(Exception):
                self.context.close()
        if self.browser is not None:
            with suppress(Exception):
                self.browser.close()
        self.context = None
        self.browser = None

    def __enter__(self) -> "BrowserSession":
        return self.start()

    def __exit__(self, *exc_info: object) -> None:
        self.close()
