"""Engine tests using a fake browser session — no network, no real browser."""

from __future__ import annotations

import unittest

from scraper.core.engine import collect_products, scrape_product_reviews
from scraper.core.models import ProductRecord, SubcategoryTarget
from scraper.sites.base import SiteAdapter


class FakeSession:
    """Returns canned HTML per URL and records the calls."""

    def __init__(self, pages: dict[str, str | None]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str, **_kwargs: object) -> str | None:
        self.calls.append(url)
        return self.pages.get(url)


class FakeAdapter(SiteAdapter):
    name = "fake"
    label = "Fake"
    base_url = "http://x"
    home_url = "http://x"
    max_listing_pages = 5
    reviews_per_page_guess = 2

    def build_search_url(self, query: str) -> str:
        return "http://x/search"

    def build_listing_page_url(self, search_url: str, page_number: int) -> str:
        return f"{search_url}?page={page_number}"

    def parse_products(self, html, category, subcategory, source_url, max_records):
        ids = [piece for piece in html.split(",") if piece]
        records = []
        for product_id in ids:
            records.append(
                ProductRecord(
                    site=self.name,
                    category=category,
                    subcategory=subcategory,
                    title=product_id,
                    price="",
                    rating="",
                    ratings_count="",
                    reviews_count="",
                    product_url=f"http://x/p/{product_id}",
                    product_id=product_id,
                    source_url=source_url,
                )
            )
            if len(records) >= max_records:
                break
        return records

    def get_reviews_url(self, product_url: str) -> str:
        return "http://x/rev"

    def build_review_page_url(self, reviews_url: str, page_number: int) -> str:
        return f"{reviews_url}?p={page_number}"

    def parse_reviews(self, html, product_url, product_name):
        return [{"rating": "5", "title": piece, "body": piece} for piece in html.split(",") if piece]


class CollectProductsTest(unittest.TestCase):
    def test_paginates_and_caps_at_max(self) -> None:
        session = FakeSession(
            {
                "http://x/search?page=1": "p1,p2,p3",
                "http://x/search?page=2": "p4,p5",
            }
        )
        records = collect_products(
            FakeAdapter(),
            category="C",
            subcategory="S",
            query="q",
            session=session,
            max_products=4,
            retries=0,
        )
        self.assertEqual([r.product_id for r in records], ["p1", "p2", "p3", "p4"])

    def test_stops_after_consecutive_empty_pages(self) -> None:
        session = FakeSession(
            {
                "http://x/search?page=1": "a,b",
                "http://x/search?page=2": "",  # empty -> counts as empty page
                # pages 3,4 return None -> empty pages; 3 in a row stops the loop
            }
        )
        records = collect_products(
            FakeAdapter(),
            category="C",
            subcategory="S",
            query="q",
            session=session,
            max_products=100,
            retries=0,
        )
        self.assertEqual([r.product_id for r in records], ["a", "b"])
        # Should not have walked all 5 allowed pages.
        self.assertLessEqual(len(session.calls), 4)

    def test_dedupes_repeated_urls(self) -> None:
        session = FakeSession(
            {
                "http://x/search?page=1": "a,b",
                "http://x/search?page=2": "b,c",  # b repeats
            }
        )
        records = collect_products(
            FakeAdapter(),
            category="C",
            subcategory="S",
            query="q",
            session=session,
            max_products=10,
            retries=0,
        )
        self.assertEqual([r.product_id for r in records], ["a", "b", "c"])


class ScrapeReviewsTest(unittest.TestCase):
    def _product(self) -> ProductRecord:
        return ProductRecord(
            site="fake",
            category="C",
            subcategory="S",
            title="T",
            price="",
            rating="",
            ratings_count="",
            reviews_count="",
            product_url="http://x/p/1",
            product_id="1",
            source_url="",
        )

    def test_collects_until_empty_page(self) -> None:
        session = FakeSession(
            {
                "http://x/rev?p=1": "r1,r2",
                "http://x/rev?p=2": "r3",
                "http://x/rev?p=3": "",  # empty -> stop
            }
        )
        reviews, status, error = scrape_product_reviews(
            FakeAdapter(),
            self._product(),
            session=session,
            max_reviews=0,
            retries=0,
        )
        self.assertEqual(status, "success")
        self.assertEqual(error, "")
        self.assertEqual([r["title"] for r in reviews], ["r1", "r2", "r3"])

    def test_respects_max_reviews_cap(self) -> None:
        session = FakeSession(
            {
                "http://x/rev?p=1": "r1,r2",
                "http://x/rev?p=2": "r3,r4",
            }
        )
        reviews, status, _ = scrape_product_reviews(
            FakeAdapter(),
            self._product(),
            session=session,
            max_reviews=3,
            retries=0,
        )
        self.assertEqual(status, "success")
        self.assertEqual(len(reviews), 3)

    def test_dedupes_and_stops_when_page_repeats(self) -> None:
        # Amazon-style bug: every pageNumber re-serves the same reviews.
        session = FakeSession(
            {
                "http://x/rev?p=1": "a,b",
                "http://x/rev?p=2": "a,b",  # no new reviews -> must stop here
                "http://x/rev?p=3": "c",  # must never be fetched
            }
        )
        reviews, status, _ = scrape_product_reviews(
            FakeAdapter(),
            self._product(),
            session=session,
            max_reviews=0,
            retries=0,
        )
        self.assertEqual(status, "success")
        self.assertEqual([r["title"] for r in reviews], ["a", "b"])
        self.assertNotIn("http://x/rev?p=3", session.calls)

    def test_empty_first_page_reports_empty(self) -> None:
        session = FakeSession({"http://x/rev?p=1": ""})
        reviews, status, _ = scrape_product_reviews(
            FakeAdapter(),
            self._product(),
            session=session,
            max_reviews=0,
            retries=0,
        )
        self.assertEqual(status, "empty")
        self.assertEqual(reviews, [])


class TargetTest(unittest.TestCase):
    def test_search_query_defaults_to_subcategory(self) -> None:
        self.assertEqual(SubcategoryTarget("C", "Smartphones").search_query(), "Smartphones")
        self.assertEqual(SubcategoryTarget("C", "S", "phones").search_query(), "phones")


if __name__ == "__main__":
    unittest.main()
