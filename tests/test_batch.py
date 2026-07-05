"""Batch helper tests: CSV loading, resume ledger, and row normalization."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scraper.core.batch import (
    _load_completed_keys,
    _review_rows_for_product,
    load_products_from_dir,
)
from scraper.core.models import PRODUCT_CSV_FIELDS, ProductRecord
from scraper.core.textutils import slugify
from scraper.sites.flipkart import FlipkartAdapter


class SlugifyTest(unittest.TestCase):
    def test_slugify(self) -> None:
        self.assertEqual(slugify("Beauty & Care__Bath & Body"), "beauty-care-bath-body")
        self.assertEqual(slugify("   "), "unknown")


class LoadProductsTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_dir = Path(tmp)
            csv_path = product_dir / "cat.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=PRODUCT_CSV_FIELDS)
                writer.writeheader()
                writer.writerow(
                    {
                        "site": "flipkart",
                        "category": "Electronics",
                        "subcategory": "Smartphones",
                        "title": "Phone X",
                        "price": "₹100",
                        "rating": "4.1",
                        "ratings_count": "10",
                        "reviews_count": "2",
                        "product_url": "http://x/p/1",
                        "product_id": "PID1",
                        "source_url": "src",
                    }
                )
                # A row with no URL should be skipped.
                writer.writerow({field: "" for field in PRODUCT_CSV_FIELDS})

            products = load_products_from_dir(product_dir)
            self.assertEqual(len(products), 1)
            self.assertEqual(products[0].product_id, "PID1")
            self.assertEqual(products[0].title, "Phone X")


class ResumeLedgerTest(unittest.TestCase):
    def test_completed_keys_only_terminal_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            status_path = output_dir / "product_review_status.csv"
            with status_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["product_id", "product_url", "status"]
                )
                writer.writeheader()
                writer.writerow({"product_id": "A", "product_url": "u1", "status": "success"})
                writer.writerow({"product_id": "B", "product_url": "u2", "status": "empty"})
                writer.writerow({"product_id": "", "product_url": "u3", "status": "failed"})
                writer.writerow({"product_id": "D", "product_url": "u4", "status": "running"})

            keys = _load_completed_keys(output_dir)
            # success + empty are terminal; "failed" is retryable (throttle recovery)
            # and "running" is not terminal.
            self.assertEqual(keys, {"A", "B"})
            self.assertNotIn("u3", keys)  # failed -> retried on resume
            self.assertNotIn("D", keys)


class ReviewRowTest(unittest.TestCase):
    def test_normalization_copies_product_metadata(self) -> None:
        product = ProductRecord(
            site="flipkart",
            category="Electronics",
            subcategory="Smartphones",
            title="Phone X",
            price="₹100",
            rating="4.1",
            ratings_count="10",
            reviews_count="2",
            product_url="http://x/p/1",
            product_id="PID1",
            source_url="src",
        )
        raw = [{"rating": 5.0, "title": "Great", "body": "Nice", "helpful_count": 3}]
        rows = _review_rows_for_product(FlipkartAdapter(), product, raw)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["product_title"], "Phone X")
        self.assertEqual(row["product_listing_rating"], "4.1")
        self.assertEqual(row["review_rating"], "5.0")
        self.assertEqual(row["review_title"], "Great")
        self.assertEqual(row["helpful_count"], "3")
        self.assertEqual(row["site"], "flipkart")


if __name__ == "__main__":
    unittest.main()
