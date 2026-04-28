"""Scrape Flipkart reviews from the current React Native Web review pages."""

from __future__ import annotations

import re
import urllib.parse

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import BrowserContext
from tqdm import tqdm

from scraper.utils import get_page_html

_RATING_NODE_SELECTOR = "div.css-146c3p1"
_RATING_TEXT_PATTERN = re.compile(r"^\d\.\d$")
_DATE_TEXT_PATTERN = re.compile(
    r"(?:Verified Purchase\s*[·•]\s*)?"
    r"\d+\s+"
    r"(?:minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)"
    r"\s+ago",
    re.IGNORECASE,
)
_HELPFUL_COUNT_PATTERN = re.compile(r"Helpful for\s+(\d[\d,]*)", re.IGNORECASE)
_VARIANT_PATTERN = re.compile(r"^Review for:\s*(.+)$", re.IGNORECASE)
_CITY_PATTERN = re.compile(r"^,\s*(.+)$")
_REVIEWER_BADGE_PATTERN = re.compile(
    r"^(?:Gold|Silver|Bronze)\s+Reviewer$",
    re.IGNORECASE,
)
_IGNORED_TEXT_VALUES = {
    "read more",
    "read less",
    "report abuse",
}
_REVIEWS_PER_PAGE = 10


def get_reviews_url(product_url: str) -> str:
    """Return the Flipkart review page base URL for a product URL."""

    parsed_url = urllib.parse.urlparse(product_url)
    path_match = re.search(r"^(?P<prefix>.+)/p/(?P<product_id>[^/?#]+)$", parsed_url.path)

    if path_match is None:
        raise ValueError(f"Could not extract Flipkart product id from URL: {product_url}")

    reviews_path = re.sub(r"/p/", "/product-reviews/", parsed_url.path, count=1)
    return urllib.parse.urlunparse(
        parsed_url._replace(
            path=reviews_path,
            params="",
            query="",
            fragment="",
        ),
    )


def _build_review_page_url(review_page_base_url: str, page_number: int) -> str:
    """Return a paginated Flipkart review page URL."""

    return urllib.parse.urlunparse(
        urllib.parse.urlparse(review_page_base_url)._replace(
            query=urllib.parse.urlencode({"page": page_number}),
        ),
    )


def _get_rating_nodes(page_soup: BeautifulSoup) -> list[Tag]:
    """Return rating nodes that match the verified one-decimal review rating format."""

    rating_nodes: list[Tag] = []

    for node in page_soup.select(_RATING_NODE_SELECTOR):
        if not isinstance(node, Tag):
            continue

        rating_text = node.get_text(" ", strip=True)

        if _RATING_TEXT_PATTERN.fullmatch(rating_text) is not None:
            rating_nodes.append(node)

    return rating_nodes


def _get_review_block_from_rating_node(rating_node: Tag) -> Tag | None:
    """Walk three parent levels up from the rating node to reach the review block."""

    review_block: Tag | None = rating_node

    # Flipkart's current RNW review DOM consistently places the card container
    # three levels above the numeric rating node.
    for _ in range(3):
        parent = review_block.parent if review_block is not None else None

        if not isinstance(parent, Tag):
            return None

        review_block = parent

    return review_block


def _get_review_texts(review_block: Tag) -> list[str]:
    """Return normalized text chunks from a review block in DOM order."""

    texts: list[str] = []
    previous_text = ""

    for text in review_block.stripped_strings:
        normalized_text = re.sub(r"\s+", " ", text).strip()

        if not normalized_text:
            continue

        if normalized_text.lower() in _IGNORED_TEXT_VALUES:
            continue

        if normalized_text == previous_text:
            continue

        texts.append(normalized_text)
        previous_text = normalized_text

    return texts


def _extract_date(texts: list[str]) -> str:
    """Return the first relative-date text found in the review text chunks."""

    for text in texts:
        match = _DATE_TEXT_PATTERN.search(text)

        if match is not None:
            return match.group(0).strip()

    combined_text = " | ".join(texts)
    match = _DATE_TEXT_PATTERN.search(combined_text)

    if match is None:
        return ""

    return match.group(0).strip()


def _extract_helpful_count(texts: list[str]) -> int:
    """Return the helpful count found in the review text chunks, if any."""

    for text in texts:
        match = _HELPFUL_COUNT_PATTERN.search(text)

        if match is not None:
            return int(match.group(1).replace(",", ""))

    combined_text = " | ".join(texts)
    match = _HELPFUL_COUNT_PATTERN.search(combined_text)

    if match is None:
        return 0

    return int(match.group(1).replace(",", ""))


def _extract_city(text: str) -> str:
    """Return a normalized city name from a city text chunk."""

    match = _CITY_PATTERN.fullmatch(text)

    if match is None:
        return ""

    return match.group(1).strip()


def _is_metadata_text(text: str) -> bool:
    """Return whether a text chunk is review metadata rather than review content."""

    if not text:
        return True

    return any(
        (
            _DATE_TEXT_PATTERN.search(text) is not None,
            _HELPFUL_COUNT_PATTERN.search(text) is not None,
            _VARIANT_PATTERN.fullmatch(text) is not None,
            _CITY_PATTERN.fullmatch(text) is not None,
            _REVIEWER_BADGE_PATTERN.fullmatch(text) is not None,
        ),
    )


def _parse_review_block(
    review_block: Tag,
    product_url: str,
    product_name: str,
) -> dict[str, object] | None:
    """Parse a single review block into a stable review record."""

    texts = _get_review_texts(review_block)

    if not texts:
        return None

    rating_text = texts[0]

    if _RATING_TEXT_PATTERN.fullmatch(rating_text) is None:
        return None

    title = texts[2] if len(texts) > 2 else ""
    variant = ""
    body_index = 3

    if len(texts) > 3:
        variant_match = _VARIANT_PATTERN.fullmatch(texts[3])

        if variant_match is not None:
            variant = variant_match.group(1).strip()
            body_index = 4

    body = texts[body_index] if len(texts) > body_index else ""

    if _is_metadata_text(body):
        body = ""

    reviewer_index = body_index + 1
    reviewer = texts[reviewer_index] if len(texts) > reviewer_index else ""

    if _is_metadata_text(reviewer):
        reviewer = ""

    city = ""
    badge_index = reviewer_index + 1

    if len(texts) > reviewer_index + 1:
        possible_city = _extract_city(texts[reviewer_index + 1])

        if possible_city:
            city = possible_city
            badge_index = reviewer_index + 2

    reviewer_badge = ""

    if len(texts) > badge_index:
        possible_badge = texts[badge_index]

        if _REVIEWER_BADGE_PATTERN.fullmatch(possible_badge) is not None:
            reviewer_badge = possible_badge

    if not any([title, body, reviewer]):
        return None

    return {
        "product_url": product_url,
        "product_name": product_name,
        "rating": float(rating_text),
        "title": title,
        "body": body,
        "reviewer": reviewer,
        "date": _extract_date(texts),
        "helpful_count": _extract_helpful_count(texts),
        "variant": variant,
        "city": city,
        "reviewer_badge": reviewer_badge,
    }


def _extract_reviews_from_page(
    page_soup: BeautifulSoup,
    product_url: str,
    product_name: str,
) -> list[dict[str, object]]:
    """Extract review records from a parsed Flipkart review page."""

    reviews: list[dict[str, object]] = []
    seen_review_blocks: set[int] = set()

    for rating_node in _get_rating_nodes(page_soup):
        review_block = _get_review_block_from_rating_node(rating_node)

        if review_block is None:
            continue

        review_block_id = id(review_block)

        if review_block_id in seen_review_blocks:
            continue

        seen_review_blocks.add(review_block_id)
        review_record = _parse_review_block(review_block, product_url, product_name)

        if review_record is not None:
            reviews.append(review_record)

    # Each current review page renders ten reviews. If more matches leak through,
    # they are almost certainly non-review rating widgets rather than extra cards.
    return reviews


def scrape_reviews(
    product_url: str,
    context: BrowserContext,
    product_name: str = "",
) -> list[dict[str, object]]:
    """Scrape all review entries for a single Flipkart product."""

    reviews: list[dict[str, object]] = []
    review_page_base_url = get_reviews_url(product_url)
    page_number = 1

    with tqdm(desc="Review pages scraped", unit="page") as progress:
        while True:
            review_page_url = _build_review_page_url(review_page_base_url, page_number)
            html = get_page_html(context, review_page_url)
            progress.update(1)

            if html is None:
                break

            page_soup = BeautifulSoup(html, "lxml")
            page_reviews = _extract_reviews_from_page(page_soup, product_url, product_name)

            if not page_reviews:
                break

            reviews.extend(page_reviews)

            if not page_reviews:
                break

            page_number += 1

    return reviews
