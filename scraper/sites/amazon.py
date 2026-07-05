"""Amazon.in adapter (listing + reviews).

Amazon search result cards are stable around ``data-component-type`` and ASINs,
and reviews hang off ``data-hook`` attributes. Amazon is, however, aggressive
about bot detection: expect CAPTCHA / "automated access" interstitials on
unauthenticated, high-rate runs. Use modest concurrency and delays, and treat
this adapter as best-effort that may need live selector tuning.
"""

from __future__ import annotations

import html as htmllib
import json
import re
import time
from contextlib import suppress
from urllib.parse import quote_plus, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from scraper.core.models import ProductRecord, SubcategoryTarget
from scraper.core.textutils import normalize_text
from scraper.sites.base import SiteAdapter

_BASE_URL = "https://www.amazon.in"
_ASIN_PATTERN = re.compile(r"/(?:dp|gp/product|product-reviews)/([A-Z0-9]{10})")
_RATING_PATTERN = re.compile(r"([0-5](?:\.\d)?)\s+out of 5")
_DIGITS_PATTERN = re.compile(r"[\d,]+")
_REVIEW_TITLE_PREFIX = re.compile(r"^\s*[0-5](?:\.\d)?\s+out of 5 stars\s*", re.IGNORECASE)
_REVIEWS_STATE_PATTERN = re.compile(r'data-state="(\{[^"]*reviewsCsrfToken[^"]*\})"')

# JS run inside the logged-in review page: it POSTs Amazon's own reviews AJAX
# endpoint (same-origin, so cookies + session ride along) and returns the raw
# "&&&"-delimited response text.
_AMAZON_REVIEWS_FETCH_JS = (
    "async ({ajax, ref, body, token}) => {"
    "  const r = await fetch(ajax + 'ref=' + ref, {"
    "    method: 'POST',"
    "    headers: {"
    "      'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',"
    "      'anti-csrftoken-a2z': token,"
    "      'x-requested-with': 'XMLHttpRequest'"
    "    },"
    "    body"
    "  });"
    "  return await r.text();"
    "}"
)


def _amazon_join_fragments(ajax_text: str) -> str:
    """Concatenate the HTML fragments out of Amazon's ``&&&`` review stream."""

    parts: list[str] = []
    for chunk in ajax_text.split("&&&"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            arr = json.loads(chunk)
        except (json.JSONDecodeError, ValueError):
            continue
        for element in arr if isinstance(arr, list) else []:
            if isinstance(element, str) and "<" in element:
                parts.append(element)
    return "".join(parts)


def _amazon_next_cursor(html: str) -> tuple[str, dict]:
    """Return the (reftag, params) for the next review page, or ('', {}).

    Amazon paginates reviews with a stateful cursor: each response embeds a
    ``show-more-button`` whose ``data-reviews-state-param`` carries the
    ``nextPageToken`` for the following page.
    """

    button = BeautifulSoup(html, "lxml").select_one('[data-hook="show-more-button"]')
    if button is None:
        return "", {}
    try:
        params = json.loads(button.get("data-reviews-state-param", "") or "{}")
    except (json.JSONDecodeError, ValueError):
        params = {}
    return button.get("data-reftag", "") or "", params


def _text(node: Tag | None) -> str:
    return normalize_text(node.get_text(" ", strip=True)) if isinstance(node, Tag) else ""


def _asin_from_url(url: str) -> str:
    match = _ASIN_PATTERN.search(url)
    return match.group(1) if match else ""


class AmazonAdapter(SiteAdapter):
    name = "amazon"
    label = "Amazon"
    base_url = _BASE_URL
    home_url = _BASE_URL
    locale = "en-IN"
    listing_ready_selector = "div[data-component-type='s-search-result'], div.s-main-slot"
    review_ready_selector = "div[data-hook='review'], div#cm_cr-review_list"
    supports_reviews = True
    max_listing_pages = 7  # Amazon caps search pages aggressively
    reviews_per_page_guess = 10
    # Amazon's edge 503-throttles clients that skip loading sub-resources, so it
    # must load resources regardless of the chosen speed profile.
    block_resources = False
    # Amazon's /product-reviews/ page is a login wall for logged-out users.
    # Key only on the login form's email field id: the "/ap/signin" header link
    # is present even on logged-in pages and would false-positive.
    auth_wall_markers = ("ap_email",)
    notes = (
        "Product listings work (no resource blocking, to clear Amazon's bot edge). "
        "REVIEWS require a logged-in Amazon session — the public review page is a "
        "sign-in wall, so review runs fail fast with a clear message unless you "
        "supply auth cookies. Use low concurrency. Best-effort."
    )

    default_targets = [
        SubcategoryTarget("Electronics", "Smartphones", "smartphones"),
        SubcategoryTarget("Electronics", "Laptops", "laptops"),
        SubcategoryTarget("Electronics", "Headphones", "headphones"),
        SubcategoryTarget("Electronics", "Smartwatches", "smart watches"),
        SubcategoryTarget("Electronics", "Televisions", "smart tv"),
        SubcategoryTarget("Home", "Kitchen Appliances", "kitchen appliances"),
        SubcategoryTarget("Beauty & Care", "Skincare", "face moisturizer"),
        SubcategoryTarget("Clothing", "Mens Wear", "men t shirt"),
        SubcategoryTarget("Clothing", "Womens Wear", "women kurta"),
        SubcategoryTarget("Footwear", "Mens Footwear", "men shoes"),
    ]

    # -- URLs --------------------------------------------------------------- #
    def build_search_url(self, query: str) -> str:
        return f"{_BASE_URL}/s?k={quote_plus(query)}"

    def build_listing_page_url(self, search_url: str, page_number: int) -> str:
        separator = "&" if "?" in search_url else "?"
        return f"{search_url}{separator}page={page_number}"

    def get_reviews_url(self, product_url: str) -> str:
        asin = _asin_from_url(product_url)
        if not asin:
            raise ValueError(f"Could not extract Amazon ASIN from URL: {product_url}")
        return f"{_BASE_URL}/product-reviews/{asin}/"

    def build_review_page_url(self, reviews_url: str, page_number: int) -> str:
        separator = "&" if "?" in reviews_url else "?"
        return f"{reviews_url}{separator}pageNumber={page_number}&reviewerType=all_reviews"

    # -- Parsing ------------------------------------------------------------ #
    def parse_products(
        self,
        html: str,
        category: str,
        subcategory: str,
        source_url: str,
        max_records: int,
    ) -> list[ProductRecord]:
        soup = BeautifulSoup(html, "lxml")
        records: list[ProductRecord] = []
        seen: set[str] = set()

        cards = soup.select("div[data-component-type='s-search-result']")
        for card in cards:
            if not isinstance(card, Tag):
                continue
            asin = (card.get("data-asin") or "").strip()
            link = card.select_one("h2 a") or card.select_one("a.a-link-normal.s-no-outline")
            href = str(link["href"]).strip() if isinstance(link, Tag) and link.get("href") else ""
            if not href and not asin:
                continue

            product_url = (
                f"{_BASE_URL}/dp/{asin}" if asin else urljoin(_BASE_URL, href.split("?", 1)[0])
            )
            if product_url in seen:
                continue
            seen.add(product_url)

            title = (
                _text(card.select_one("h2 a span"))
                or _text(card.select_one("h2 span"))
                or _text(card.select_one("h2"))
            )
            price = _text(card.select_one("span.a-price span.a-offscreen"))
            rating_text = _text(card.select_one("span.a-icon-alt"))
            rating_match = _RATING_PATTERN.search(rating_text)
            count_node = card.select_one(
                "span.a-size-base.s-underline-text"
            ) or card.select_one("a[href*='customerReviews'] span")
            count_text = _text(count_node)
            count_match = _DIGITS_PATTERN.search(count_text)

            records.append(
                ProductRecord(
                    site=self.name,
                    category=category,
                    subcategory=subcategory,
                    title=title or "Unknown product",
                    price=price,
                    rating=rating_match.group(1) if rating_match else "",
                    ratings_count=count_match.group(0) if count_match else "",
                    reviews_count="",
                    product_url=product_url,
                    product_id=asin or _asin_from_url(product_url),
                    source_url=source_url,
                )
            )
            if len(records) >= max_records:
                break
        return records

    def parse_reviews(
        self,
        html: str,
        product_url: str,
        product_name: str,
    ) -> list[dict[str, object]]:
        soup = BeautifulSoup(html, "lxml")
        reviews: list[dict[str, object]] = []

        # Review entries are <li data-hook="review"> (not <div>), so match any tag.
        for card in soup.select("[data-hook='review']"):
            if not isinstance(card, Tag):
                continue
            rating_text = _text(
                card.select_one("i[data-hook='review-star-rating'] span.a-icon-alt")
                or card.select_one("i[data-hook='cmps-review-star-rating'] span.a-icon-alt")
            )
            rating_match = _RATING_PATTERN.search(rating_text)

            title_node = card.select_one("[data-hook='review-title']")
            # The title node text is prefixed with "x.x out of 5 stars"; strip it.
            title = ""
            if isinstance(title_node, Tag):
                title = _REVIEW_TITLE_PREFIX.sub("", _text(title_node)).strip()

            body = _text(card.select_one("span[data-hook='review-body']"))
            reviewer = _text(card.select_one("span.a-profile-name"))

            date_text = _text(card.select_one("span[data-hook='review-date']"))
            date = date_text.split(" on ", 1)[-1].strip() if " on " in date_text else date_text

            helpful_text = _text(card.select_one("span[data-hook='helpful-vote-statement']"))
            helpful_match = _DIGITS_PATTERN.search(helpful_text)
            helpful = int(helpful_match.group(0).replace(",", "")) if helpful_match else 0

            if not any([title, body, reviewer]):
                continue

            reviews.append(
                {
                    "rating": rating_match.group(1) if rating_match else "",
                    "title": title,
                    "body": body,
                    "reviewer": reviewer,
                    "date": date,
                    "helpful_count": helpful,
                    "variant": "",
                    "city": "",
                    "reviewer_badge": "",
                }
            )
        return reviews

    # -- Deep review pagination (AJAX cursor) ------------------------------- #
    def scrape_reviews_via_session(
        self,
        session,
        product,
        *,
        max_reviews: int = 0,
        retries: int = 2,
        settle_ms: int = 650,
        empty_retry_settle_ms: int = 1500,
        page_delay_seconds: float = 0.0,
    ) -> tuple[list[dict[str, object]], str, str] | None:
        """Pull deep reviews via Amazon's own ``reviews/get`` AJAX cursor.

        The public review page only renders ~10 reviews and ``?pageNumber=N``
        re-serves page 1. Amazon's live "show more" instead POSTs an AJAX
        endpoint carrying a ``nextPageToken`` cursor. We replicate that call
        *inside the logged-in page* (so cookies + CSRF ride along) and follow the
        cursor until it runs out — lifting the cap from ~10 to everything Amazon
        exposes (up to its ~hundreds/product ceiling).

        Returns ``(raw_reviews, status, error)``; ``None`` to fall back to the
        generic pager (only when there's no session context available).
        """

        from scraper.core.browser import looks_blocked

        context = getattr(session, "context", None)
        if context is None:
            session.start()
            context = getattr(session, "context", None)
        if context is None:
            return None  # let the generic pager handle it

        asin = _asin_from_url(product.product_url)
        if not asin:
            return [], "failed", "Could not extract Amazon ASIN."

        page = context.new_page()
        collected: list[dict[str, object]] = []
        seen: set[tuple] = set()
        cap = max_reviews if max_reviews > 0 else 100_000

        def _add(raw_reviews: list[dict[str, object]]) -> int:
            added = 0
            for review in raw_reviews:
                key = (
                    str(review.get("rating", "")),
                    str(review.get("title", "")),
                    str(review.get("body", "")),
                    str(review.get("reviewer", "")),
                    str(review.get("date", "")),
                )
                if key in seen:
                    continue
                seen.add(key)
                collected.append(review)
                added += 1
            return added

        def _collect_filter(star: str) -> str:
            """Follow the AJAX cursor for one star filter. Returns a status hint."""

            query = "?reviewerType=all_reviews&pageNumber=1"
            if star:
                query += f"&filterByStar={star}"
            url = f"{_BASE_URL}/product-reviews/{asin}/{query}"

            html: str | None = None
            for attempt in range(max(0, retries) + 1):
                try:
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(settle_ms / 1000.0)
                    html = page.content()
                except Exception:  # noqa: BLE001
                    html = None
                if html and not looks_blocked(html):
                    break
                html = None
                if attempt < retries:
                    time.sleep(20 * (attempt + 1))  # anti-bot throttle cooldown

            if not html:
                return "blocked"
            if self.is_auth_wall(html):
                return "auth"

            _add(self.parse_reviews(html, product.product_url, product.title))

            state = _REVIEWS_STATE_PATTERN.search(html)
            if not state:
                return "ok"  # no AJAX token; keep the ~10 already parsed
            widget = json.loads(htmllib.unescape(state.group(1)))
            token = widget.get("reviewsCsrfToken", "")
            ajax_url = widget.get("reviewsAjaxUrl", "")
            reftag, params = _amazon_next_cursor(html)

            pages = 1
            while reftag and ajax_url and token and len(collected) < cap and pages < 400:
                body = urlencode({**params, "asin": asin, "scope": "reviewsAjax1", "reftag": reftag})
                try:
                    ajax_text = page.evaluate(
                        _AMAZON_REVIEWS_FETCH_JS,
                        {"ajax": ajax_url, "ref": reftag, "body": body, "token": token},
                    )
                except Exception:  # noqa: BLE001
                    break
                if not ajax_text or looks_blocked(ajax_text):
                    break
                fragments = _amazon_join_fragments(ajax_text)
                added = _add(self.parse_reviews(fragments, product.product_url, product.title))
                reftag, params = _amazon_next_cursor(fragments)
                pages += 1
                if added == 0:
                    break
                if page_delay_seconds > 0:
                    time.sleep(page_delay_seconds)
            return "ok"

        try:
            status = _collect_filter("")  # all-stars: covers everything up to Amazon's ~100 cap
            if not collected:
                if status == "auth":
                    return [], "failed", "Amazon review pages require a logged-in session."
                if status == "blocked":
                    return [], "failed", f"Throttled/blocked on review page for {asin}."

            # All-stars caps around ~100 reviews. When we hit that ceiling and the
            # product clearly has more, sweep each star rating (its own ~100 chain)
            # to go deeper. Skipped for small products so we don't waste requests.
            if len(collected) >= 95 and len(collected) < cap:
                for star in ("five_star", "four_star", "three_star", "two_star", "one_star"):
                    if len(collected) >= cap:
                        break
                    if _collect_filter(star) == "blocked":
                        break  # throttled mid-sweep; keep what we have
                    if page_delay_seconds > 0:
                        time.sleep(page_delay_seconds)

            if max_reviews > 0:
                collected = collected[:max_reviews]
            if collected:
                return collected, "success", ""
            return [], "empty", "No reviews parsed from Amazon review pages."
        except Exception as exc:  # noqa: BLE001
            if collected:
                return collected, "success", ""
            return [], "failed", str(exc)
        finally:
            with suppress(Exception):
                page.close()
