"""The contract every marketplace adapter implements.

A :class:`SiteAdapter` is pure site knowledge: how to build search/review URLs
and how to turn a page's HTML into product and review records. All of the
expensive, generic machinery (browsing, concurrency, resume, reporting) lives in
``scraper.core`` and drives whatever adapter it is given.
"""

from __future__ import annotations

from scraper.core.models import ProductRecord, SubcategoryTarget


class ReviewsNotSupported(RuntimeError):
    """Raised when an adapter cannot resolve a review page for a product URL."""


class SiteAdapter:
    """Base class for a marketplace adapter.

    Subclasses set the class attributes and implement the parsing/URL methods.
    Sensible defaults are provided so a minimal adapter stays small.
    """

    # Identity ----------------------------------------------------------------
    name: str = ""  # machine slug, e.g. "flipkart"
    label: str = ""  # human label, e.g. "Flipkart"
    base_url: str = ""
    home_url: str = ""

    # Browser hints -----------------------------------------------------------
    locale: str = "en-IN"
    user_agent: str = ""  # empty = auto-derive from the real browser version
    listing_ready_selector: str | None = None
    review_ready_selector: str | None = None

    # Capabilities ------------------------------------------------------------
    supports_reviews: bool = True
    max_listing_pages: int = 12
    reviews_per_page_guess: int = 10

    # Resource-blocking preference. None = follow the chosen speed profile.
    # Set False for sites whose anti-bot edge rejects clients that skip
    # loading sub-resources (e.g. Amazon).
    block_resources: bool | None = None

    # Lowercase markers that mean a review page is really a login/auth wall.
    # When matched, review scraping fails fast with a clear message instead of
    # timing out hunting for review nodes that will never appear.
    auth_wall_markers: tuple[str, ...] = ()

    # Content -----------------------------------------------------------------
    default_targets: list[SubcategoryTarget] = []
    notes: str = ""  # caveats surfaced in the terminal app

    # -- Browser configuration ------------------------------------------------
    def extra_headers(self) -> dict[str, str]:
        """Return extra HTTP headers to merge over the stealth defaults.

        Empty by default: the browser layer already sets a realistic UA,
        Accept-Language, client hints, and fetch-metadata. Avoid adding a global
        ``Referer`` here — sending one on every navigation is an anti-bot tell
        (it deterministically tripped Amazon's 503 edge).
        """

        return {}

    # -- Product listing ------------------------------------------------------
    def build_search_url(self, query: str) -> str:
        """Return a search URL for a free-text query."""

        raise NotImplementedError

    def build_listing_page_url(self, search_url: str, page_number: int) -> str:
        """Return a paginated listing URL for ``search_url`` and ``page_number``."""

        raise NotImplementedError

    def parse_products(
        self,
        html: str,
        category: str,
        subcategory: str,
        source_url: str,
        max_records: int,
    ) -> list[ProductRecord]:
        """Extract up to ``max_records`` product rows from one listing page."""

        raise NotImplementedError

    # -- Reviews --------------------------------------------------------------
    def is_auth_wall(self, html: str) -> bool:
        """Return whether a fetched review page is actually a login wall."""

        if not self.auth_wall_markers:
            return False
        low = html.lower()
        return any(marker in low for marker in self.auth_wall_markers)

    def get_reviews_url(self, product_url: str) -> str:
        """Return the base review URL for a product URL, or raise."""

        raise ReviewsNotSupported(
            f"{self.label} does not support review scraping for {product_url}.",
        )

    def build_review_page_url(self, reviews_url: str, page_number: int) -> str:
        """Return a paginated review URL."""

        raise NotImplementedError

    def parse_reviews(
        self,
        html: str,
        product_url: str,
        product_name: str,
    ) -> list[dict[str, object]]:
        """Extract raw review dicts (see ``RAW_REVIEW_KEYS``) from one page."""

        raise NotImplementedError
