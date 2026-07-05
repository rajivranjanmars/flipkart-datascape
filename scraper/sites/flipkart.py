"""Flipkart adapter — ported from the original Flipkart-only scraper.

Listing parsing walks up from each product anchor to a card container and reads
price/rating/counts. Review parsing targets Flipkart's React-Native-Web review
DOM, where a one-decimal rating node sits a fixed depth inside each review card.
"""

from __future__ import annotations

import re
import urllib.parse
from urllib.parse import parse_qs, quote_plus, urlparse

from bs4 import BeautifulSoup, Tag

from scraper.core.models import ProductRecord, SubcategoryTarget
from scraper.core.textutils import normalize_text
from scraper.sites.base import SiteAdapter

_BASE_URL = "https://www.flipkart.com"

# -- Listing patterns ------------------------------------------------------- #
_PRICE_PATTERN = re.compile(r"₹\s*[\d,]+")
_RATING_PATTERN = re.compile(r"(?<!\d)([1-5]\.\d)(?!\d)")
_RATING_WITH_COUNTS_PATTERN = re.compile(
    r"(?<!\d)([1-5]\.\d)(?!\d).{0,40}?[\d,]+\s+Ratings?",
    re.IGNORECASE,
)
_RATINGS_COUNT_PATTERN = re.compile(r"([\d,]+)\s+Ratings?", re.IGNORECASE)
_REVIEWS_COUNT_PATTERN = re.compile(r"([\d,]+)\s+Reviews?", re.IGNORECASE)

# -- Review patterns -------------------------------------------------------- #
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
_REVIEWER_BADGE_PATTERN = re.compile(r"^(?:Gold|Silver|Bronze)\s+Reviewer$", re.IGNORECASE)
_IGNORED_TEXT_VALUES = {"read more", "read less", "report abuse"}


# --------------------------------------------------------------------------- #
# Listing helpers
# --------------------------------------------------------------------------- #
def _absolute_product_url(href: str) -> str:
    normalized = href.split("#", maxsplit=1)[0]
    if normalized.startswith("http"):
        return normalized
    return f"{_BASE_URL}{normalized}"


def _extract_product_id(product_url: str) -> str:
    parsed = urlparse(product_url)
    params = parse_qs(parsed.query)
    if params.get("pid"):
        return params["pid"][0]
    parts = [p for p in parsed.path.split("/") if p]
    if "p" in parts:
        idx = parts.index("p")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _find_card_container(anchor: Tag) -> Tag:
    current: Tag = anchor
    best: Tag = anchor
    for _ in range(5):
        parent = current.parent
        if not isinstance(parent, Tag):
            break
        if _PRICE_PATTERN.search(normalize_text(parent.get_text(" ", strip=True))) is not None:
            return parent
        best = parent
        current = parent
    return best


def _title_from_url(product_url: str) -> str:
    parts = [p for p in urlparse(product_url).path.split("/") if p]
    if not parts:
        return ""
    return normalize_text(parts[0].replace("-", " "))


def _is_noisy_title(candidate: str, slug_title: str) -> bool:
    text = normalize_text(candidate)
    if not text:
        return True
    lower = text.lower()
    if lower.startswith("add to compare") or lower in {"off on exchange", "bank offer"}:
        return True
    if "ratings" in lower or "reviews" in lower:
        return True
    if _RATING_PATTERN.fullmatch(text.split(" ", maxsplit=1)[0]):
        return True
    if _PRICE_PATTERN.search(text) is not None:
        return True
    if len(text) > 140:
        return True
    if slug_title and len(text) < 12:
        return True
    if slug_title and " strap" in lower:
        return True
    return False


def _extract_title(anchor: Tag, card: Tag, product_url: str) -> str:
    slug_title = _title_from_url(product_url)
    candidates = [anchor.get("title", ""), anchor.get_text(" ", strip=True)]
    for node in card.find_all(["div", "span"], recursive=True):
        if not isinstance(node, Tag):
            continue
        text = normalize_text(node.get_text(" ", strip=True))
        if text and _PRICE_PATTERN.search(text) is None:
            candidates.append(text)
    for candidate in candidates:
        title = normalize_text(str(candidate))
        if title and "/p/" not in title and not _is_noisy_title(title, slug_title):
            return title
    return slug_title or "Unknown product"


def _extract_counts(card_text: str) -> tuple[str, str]:
    ratings = _RATINGS_COUNT_PATTERN.search(card_text)
    reviews = _REVIEWS_COUNT_PATTERN.search(card_text)
    return (ratings.group(1) if ratings else "", reviews.group(1) if reviews else "")


def _extract_rating(card_text: str) -> str:
    match = _RATING_WITH_COUNTS_PATTERN.search(card_text)
    return match.group(1) if match else ""


# --------------------------------------------------------------------------- #
# Review helpers
# --------------------------------------------------------------------------- #
def _rating_nodes(soup: BeautifulSoup) -> list[Tag]:
    nodes: list[Tag] = []
    for node in soup.select(_RATING_NODE_SELECTOR):
        if isinstance(node, Tag) and _RATING_TEXT_PATTERN.fullmatch(node.get_text(" ", strip=True)):
            nodes.append(node)
    return nodes


def _review_block(rating_node: Tag) -> Tag | None:
    block: Tag | None = rating_node
    for _ in range(3):
        parent = block.parent if block is not None else None
        if not isinstance(parent, Tag):
            return None
        block = parent
    return block


def _review_texts(block: Tag) -> list[str]:
    texts: list[str] = []
    previous = ""
    for text in block.stripped_strings:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized or normalized.lower() in _IGNORED_TEXT_VALUES or normalized == previous:
            continue
        texts.append(normalized)
        previous = normalized
    return texts


def _extract_date(texts: list[str]) -> str:
    for text in texts:
        match = _DATE_TEXT_PATTERN.search(text)
        if match:
            return match.group(0).strip()
    match = _DATE_TEXT_PATTERN.search(" | ".join(texts))
    return match.group(0).strip() if match else ""


def _extract_helpful(texts: list[str]) -> int:
    for text in texts:
        match = _HELPFUL_COUNT_PATTERN.search(text)
        if match:
            return int(match.group(1).replace(",", ""))
    match = _HELPFUL_COUNT_PATTERN.search(" | ".join(texts))
    return int(match.group(1).replace(",", "")) if match else 0


def _is_metadata(text: str) -> bool:
    if not text:
        return True
    return any(
        (
            _DATE_TEXT_PATTERN.search(text) is not None,
            _HELPFUL_COUNT_PATTERN.search(text) is not None,
            _VARIANT_PATTERN.fullmatch(text) is not None,
            _CITY_PATTERN.fullmatch(text) is not None,
            _REVIEWER_BADGE_PATTERN.fullmatch(text) is not None,
        )
    )


def _parse_review_block(block: Tag) -> dict[str, object] | None:
    texts = _review_texts(block)
    if not texts or _RATING_TEXT_PATTERN.fullmatch(texts[0]) is None:
        return None

    title = texts[2] if len(texts) > 2 else ""
    variant = ""
    body_index = 3
    if len(texts) > 3:
        variant_match = _VARIANT_PATTERN.fullmatch(texts[3])
        if variant_match:
            variant = variant_match.group(1).strip()
            body_index = 4

    body = texts[body_index] if len(texts) > body_index else ""
    if _is_metadata(body):
        body = ""

    reviewer_index = body_index + 1
    reviewer = texts[reviewer_index] if len(texts) > reviewer_index else ""
    if _is_metadata(reviewer):
        reviewer = ""

    city = ""
    badge_index = reviewer_index + 1
    if len(texts) > reviewer_index + 1:
        city_match = _CITY_PATTERN.fullmatch(texts[reviewer_index + 1])
        if city_match:
            city = city_match.group(1).strip()
            badge_index = reviewer_index + 2

    reviewer_badge = ""
    if len(texts) > badge_index and _REVIEWER_BADGE_PATTERN.fullmatch(texts[badge_index]):
        reviewer_badge = texts[badge_index]

    if not any([title, body, reviewer]):
        return None

    return {
        "rating": float(texts[0]),
        "title": title,
        "body": body,
        "reviewer": reviewer,
        "date": _extract_date(texts),
        "helpful_count": _extract_helpful(texts),
        "variant": variant,
        "city": city,
        "reviewer_badge": reviewer_badge,
    }


# --------------------------------------------------------------------------- #
# Adapter
# --------------------------------------------------------------------------- #
class FlipkartAdapter(SiteAdapter):
    name = "flipkart"
    label = "Flipkart"
    base_url = _BASE_URL
    home_url = _BASE_URL
    locale = "en-IN"
    listing_ready_selector = "a[href*='/p/']"
    review_ready_selector = "div.css-146c3p1"
    supports_reviews = True
    max_listing_pages = 12
    reviews_per_page_guess = 10
    notes = "Mature adapter ported from the original scraper. Most reliable of the four."

    default_targets = [
        SubcategoryTarget("Beauty & Care", "Bath & Body"),
        SubcategoryTarget("Beauty & Care", "Fragrances"),
        SubcategoryTarget("Beauty & Care", "Hair Care"),
        SubcategoryTarget("Beauty & Care", "Men Grooming"),
        SubcategoryTarget("Beauty & Care", "Women Makeup"),
        SubcategoryTarget("Beauty & Care", "Women Skincare"),
        SubcategoryTarget("Clothing", "Mens wear"),
        SubcategoryTarget("Clothing", "Womens wear"),
        SubcategoryTarget("Clothing", "Kids wear"),
        SubcategoryTarget("Electronics", "Air Conditioners"),
        SubcategoryTarget("Electronics", "Laptops"),
        SubcategoryTarget("Electronics", "Refrigerators"),
        SubcategoryTarget("Electronics", "Smartphones"),
        SubcategoryTarget("Electronics", "Televisions"),
        SubcategoryTarget("Footwear", "Men Footwear"),
        SubcategoryTarget("Footwear", "Women Footwear"),
        SubcategoryTarget("Wearable Devices", "Headphones"),
        SubcategoryTarget("Wearable Devices", "Smartwatches"),
    ]

    # -- URLs --------------------------------------------------------------- #
    def build_search_url(self, query: str) -> str:
        return f"{_BASE_URL}/search?q={quote_plus(query)}"

    def build_listing_page_url(self, search_url: str, page_number: int) -> str:
        separator = "&" if "?" in search_url else "?"
        return f"{search_url}{separator}page={page_number}"

    def get_reviews_url(self, product_url: str) -> str:
        parsed = urllib.parse.urlparse(product_url)
        if "/p/" not in parsed.path:
            raise ValueError(f"Could not extract Flipkart product id from URL: {product_url}")
        reviews_path = re.sub(r"/p/", "/product-reviews/", parsed.path, count=1)
        return urllib.parse.urlunparse(
            parsed._replace(path=reviews_path, params="", query="", fragment="")
        )

    def build_review_page_url(self, reviews_url: str, page_number: int) -> str:
        return urllib.parse.urlunparse(
            urllib.parse.urlparse(reviews_url)._replace(
                query=urllib.parse.urlencode({"page": page_number})
            )
        )

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

        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue
            href = str(anchor["href"]).strip()
            if "/p/" not in href:
                continue
            product_url = _absolute_product_url(href)
            if product_url in seen:
                continue
            seen.add(product_url)

            card = _find_card_container(anchor)
            card_text = normalize_text(card.get_text(" ", strip=True))
            price_match = _PRICE_PATTERN.search(card_text)
            ratings_count, reviews_count = _extract_counts(card_text)
            records.append(
                ProductRecord(
                    site=self.name,
                    category=category,
                    subcategory=subcategory,
                    title=_extract_title(anchor, card, product_url),
                    price=price_match.group(0) if price_match else "",
                    rating=_extract_rating(card_text),
                    ratings_count=ratings_count,
                    reviews_count=reviews_count,
                    product_url=product_url,
                    product_id=_extract_product_id(product_url),
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
        seen_blocks: set[int] = set()
        for rating_node in _rating_nodes(soup):
            block = _review_block(rating_node)
            if block is None or id(block) in seen_blocks:
                continue
            seen_blocks.add(id(block))
            record = _parse_review_block(block)
            if record is not None:
                reviews.append(record)
        return reviews
