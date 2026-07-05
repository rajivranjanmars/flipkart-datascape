"""Site-agnostic data models shared by every marketplace adapter."""

from __future__ import annotations

from dataclasses import dataclass

# Raw review keys an adapter's ``parse_reviews`` is expected to populate.
# Missing keys default to an empty value when normalized into a CSV row.
RAW_REVIEW_KEYS: tuple[str, ...] = (
    "rating",
    "title",
    "body",
    "reviewer",
    "date",
    "helpful_count",
    "variant",
    "city",
    "reviewer_badge",
)


@dataclass(frozen=True)
class SubcategoryTarget:
    """A category/subcategory pair to scrape, with an optional explicit query."""

    category: str
    subcategory: str
    query: str = ""

    def search_query(self) -> str:
        """Return the query used to build a search URL for this target."""

        return self.query or self.subcategory


@dataclass(frozen=True)
class ProductRecord:
    """A normalized product listing row written to each category CSV."""

    site: str
    category: str
    subcategory: str
    title: str
    price: str
    rating: str
    ratings_count: str
    reviews_count: str
    product_url: str
    product_id: str
    source_url: str


# Column order for product listing CSVs.
PRODUCT_CSV_FIELDS: list[str] = [
    "site",
    "category",
    "subcategory",
    "title",
    "price",
    "rating",
    "ratings_count",
    "reviews_count",
    "product_url",
    "product_id",
    "source_url",
]

# Column order for review CSVs (product metadata + review fields).
REVIEW_CSV_FIELDS: list[str] = [
    "site",
    "category",
    "subcategory",
    "product_title",
    "product_price",
    "product_listing_rating",
    "product_ratings_count",
    "product_reviews_count",
    "product_url",
    "product_id",
    "source_url",
    "review_rating",
    "review_title",
    "review_body",
    "reviewer",
    "review_date",
    "helpful_count",
    "variant",
    "city",
    "reviewer_badge",
]

# Column order for the per-product status ledger that powers resume.
PRODUCT_STATUS_FIELDS: list[str] = [
    "site",
    "category",
    "subcategory",
    "product_title",
    "product_url",
    "product_id",
    "status",
    "review_count",
    "error",
]
