"""Generic, adapter-driven listing and review collection.

These functions know nothing about any particular marketplace. They drive a
:class:`~scraper.sites.base.SiteAdapter` against a long-lived
:class:`~scraper.core.browser.BrowserSession`.
"""

from __future__ import annotations

import math
import time

from scraper.core.browser import BrowserSession, looks_blocked
from scraper.core.models import ProductRecord
from scraper.sites.base import ReviewsNotSupported, SiteAdapter

_MAX_CONSECUTIVE_EMPTY_PAGES = 3


def _review_key(review: dict[str, object]) -> tuple:
    """Stable identity for a review, used to dedupe across pages."""

    return (
        str(review.get("rating", "")),
        str(review.get("title", "")),
        str(review.get("body", "")),
        str(review.get("reviewer", "")),
        str(review.get("date", "")),
    )


def _fetch_with_retries(
    session: BrowserSession,
    url: str,
    ready_selector: str | None,
    retries: int,
    settle_ms: int,
) -> str | None:
    """Fetch a URL, retrying on failures and anti-bot interstitials.

    Returns ``None`` if every attempt failed or returned a block page, so callers
    treat a persistent block as a clear failure rather than an empty page.
    """

    attempts = max(0, retries) + 1
    for attempt in range(attempts):
        html = session.fetch(url, ready_selector=ready_selector, settle_ms=settle_ms)
        if html is not None and not looks_blocked(html):
            return html
        if attempt < attempts - 1:
            if html is not None and looks_blocked(html):
                # Anti-bot throttle (e.g. Amazon's "automated access" page) needs a
                # real cooldown, not a 2s blip — escalate so the session can recover.
                time.sleep(20 * (attempt + 1))
            else:
                time.sleep(2 + attempt * 2)
    return None


def collect_products(
    adapter: SiteAdapter,
    *,
    category: str,
    subcategory: str,
    query: str,
    session: BrowserSession,
    max_products: int,
    retries: int = 2,
    settle_ms: int = 350,
) -> list[ProductRecord]:
    """Collect up to ``max_products`` product rows for one search query."""

    if max_products <= 0:
        return []

    search_url = adapter.build_search_url(query)
    records: list[ProductRecord] = []
    seen_urls: set[str] = set()
    empty_pages = 0

    for page_number in range(1, adapter.max_listing_pages + 1):
        if len(records) >= max_products:
            break

        page_url = adapter.build_listing_page_url(search_url, page_number)
        html = _fetch_with_retries(
            session,
            page_url,
            adapter.listing_ready_selector,
            retries,
            settle_ms,
        )

        if html is None:
            empty_pages += 1
            if empty_pages >= _MAX_CONSECUTIVE_EMPTY_PAGES:
                break
            continue

        page_records = adapter.parse_products(
            html,
            category,
            subcategory,
            page_url,
            max_products - len(records),
        )
        new_records = [r for r in page_records if r.product_url not in seen_urls]

        if not new_records:
            empty_pages += 1
            if empty_pages >= _MAX_CONSECUTIVE_EMPTY_PAGES:
                break
            continue

        empty_pages = 0
        for record in new_records:
            seen_urls.add(record.product_url)
            records.append(record)
            if len(records) >= max_products:
                break

    return records[:max_products]


def collect_product_urls(
    adapter: SiteAdapter,
    *,
    listing_url: str,
    session: BrowserSession,
    max_products: int,
    retries: int = 2,
    settle_ms: int = 350,
) -> list[ProductRecord]:
    """Collect product rows from an explicit listing/search URL (no query build)."""

    if max_products <= 0:
        return []

    records: list[ProductRecord] = []
    seen_urls: set[str] = set()
    empty_pages = 0

    for page_number in range(1, adapter.max_listing_pages + 1):
        if len(records) >= max_products:
            break

        page_url = adapter.build_listing_page_url(listing_url, page_number)
        html = _fetch_with_retries(
            session,
            page_url,
            adapter.listing_ready_selector,
            retries,
            settle_ms,
        )

        if html is None:
            empty_pages += 1
            if empty_pages >= _MAX_CONSECUTIVE_EMPTY_PAGES:
                break
            continue

        page_records = adapter.parse_products(
            html,
            "",
            "",
            page_url,
            max_products - len(records),
        )
        new_records = [r for r in page_records if r.product_url not in seen_urls]

        if not new_records:
            empty_pages += 1
            if empty_pages >= _MAX_CONSECUTIVE_EMPTY_PAGES:
                break
            continue

        empty_pages = 0
        for record in new_records:
            seen_urls.add(record.product_url)
            records.append(record)
            if len(records) >= max_products:
                break

    return records[:max_products]


def scrape_product_reviews(
    adapter: SiteAdapter,
    product: ProductRecord,
    *,
    session: BrowserSession,
    max_reviews: int,
    retries: int = 2,
    settle_ms: int = 350,
    empty_retry_settle_ms: int = 1500,
    page_delay_seconds: float = 0.0,
) -> tuple[list[dict[str, object]], str, str]:
    """Scrape reviews for one product.

    Returns ``(raw_reviews, status, error)`` where status is one of
    ``success`` / ``empty`` / ``failed``.
    """

    if not adapter.supports_reviews:
        return [], "failed", f"{adapter.label} review scraping is not supported."

    # A site may provide a richer, session-driven scraper (e.g. Amazon's AJAX
    # cursor for deep review pagination). Use it when present; it returns the
    # same (raw_reviews, status, error) tuple, or None to fall back here.
    custom = getattr(adapter, "scrape_reviews_via_session", None)
    if custom is not None:
        try:
            result = custom(
                session,
                product,
                max_reviews=max_reviews,
                retries=retries,
                settle_ms=settle_ms,
                empty_retry_settle_ms=empty_retry_settle_ms,
                page_delay_seconds=page_delay_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            return [], "failed", str(exc)
        if result is not None:
            return result

    try:
        reviews_url = adapter.get_reviews_url(product.product_url)
    except ReviewsNotSupported as exc:
        return [], "failed", str(exc)
    except Exception as exc:  # noqa: BLE001 - bad URL shapes should not crash a batch
        return [], "failed", str(exc)

    raw_reviews: list[dict[str, object]] = []
    seen_keys: set[tuple] = set()
    max_pages = (
        None
        if max_reviews <= 0
        else max(1, math.ceil(max_reviews / max(1, adapter.reviews_per_page_guess)))
    )
    page_number = 1

    try:
        while max_pages is None or page_number <= max_pages:
            page_url = adapter.build_review_page_url(reviews_url, page_number)
            html = _fetch_with_retries(
                session,
                page_url,
                adapter.review_ready_selector,
                retries,
                settle_ms,
            )

            if html is None:
                if raw_reviews:
                    break
                return [], "failed", f"Could not load review page: {page_url}"

            if adapter.is_auth_wall(html):
                if raw_reviews:
                    break
                return [], "failed", f"{adapter.label} review pages require a logged-in session."

            page_reviews = adapter.parse_reviews(
                html,
                product.product_url,
                product.title,
            )

            # A blank first page is often just slow hydration: retry once slower.
            if page_number == 1 and not page_reviews:
                retry_html = session.fetch(
                    page_url,
                    ready_selector=adapter.review_ready_selector,
                    settle_ms=empty_retry_settle_ms,
                )
                if retry_html is not None:
                    page_reviews = adapter.parse_reviews(
                        retry_html,
                        product.product_url,
                        product.title,
                    )

            if not page_reviews:
                break

            # Dedupe across pages. Some sites (e.g. Amazon's public review page)
            # re-serve page 1 for every pageNumber, so "page returned reviews" is
            # not enough — stop when a page adds no NEW unique reviews, or we'd
            # loop collecting the same reviews until throttled.
            new_reviews = [r for r in page_reviews if _review_key(r) not in seen_keys]
            if not new_reviews:
                break

            for review in new_reviews:
                seen_keys.add(_review_key(review))
            raw_reviews.extend(new_reviews)
            if max_reviews > 0 and len(raw_reviews) >= max_reviews:
                break

            page_number += 1
            if page_delay_seconds > 0:
                time.sleep(page_delay_seconds)
    except Exception as exc:  # noqa: BLE001 - keep one bad product from failing the batch
        if raw_reviews:
            # Partial data is still useful.
            return raw_reviews, "success", ""
        return [], "failed", str(exc)

    if max_reviews > 0:
        raw_reviews = raw_reviews[:max_reviews]

    if raw_reviews:
        return raw_reviews, "success", ""
    return [], "empty", "No reviews parsed from review pages."
