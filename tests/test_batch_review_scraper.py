from __future__ import annotations

import csv
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from scraper.batch_review_scraper import (
    ProductInput,
    ProductReviewResult,
    ReviewRow,
    append_product_artifacts,
    load_product_inputs,
    load_completed_product_keys,
    normalize_review_rows,
    parse_args,
    run_review_batch,
    write_review_artifacts,
)


class BatchReviewScraperTests(unittest.TestCase):
    """Tests for review batch loading, normalization, and artifact writing."""

    def test_load_product_inputs_reads_all_product_csvs(self) -> None:
        """Product inputs should preserve product metadata from source CSVs."""

        with TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            csv_path = temp_dir / "electronics-smartphones.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
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
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "category": "Electronics",
                        "subcategory": "Smartphones",
                        "title": "Sample Phone",
                        "price": "₹12,999",
                        "rating": "4.3",
                        "ratings_count": "1,234",
                        "reviews_count": "56",
                        "product_url": "https://www.flipkart.com/sample/p/itm?pid=MOB123",
                        "product_id": "MOB123",
                        "source_url": "https://www.flipkart.com/search?q=Smartphones",
                    },
                )

            products = load_product_inputs(temp_dir)

            self.assertEqual(len(products), 1)
            self.assertEqual(products[0].subcategory, "Smartphones")
            self.assertEqual(products[0].source_csv, "electronics-smartphones.csv")

    def test_normalize_review_rows_caps_and_copies_metadata(self) -> None:
        """Review normalization should cap rows and copy product metadata."""

        product = ProductInput(
            category="Electronics",
            subcategory="Smartphones",
            product_title="Sample Phone",
            product_price="₹12,999",
            product_listing_rating="4.3",
            product_ratings_count="1,234",
            product_reviews_count="56",
            product_url="https://www.flipkart.com/sample/p/itm?pid=MOB123",
            product_id="MOB123",
            source_url="https://www.flipkart.com/search?q=Smartphones",
            source_csv="electronics-smartphones.csv",
        )
        raw_reviews = [
            {
                "rating": 5.0,
                "title": f"Title {index}",
                "body": "Body",
                "reviewer": "Reviewer",
                "date": "1 day ago",
                "helpful_count": 1,
                "variant": "Blue",
                "city": "Delhi",
                "reviewer_badge": "Gold Reviewer",
            }
            for index in range(3)
        ]

        rows = normalize_review_rows(product, raw_reviews, max_reviews=2)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].category, "Electronics")
        self.assertEqual(rows[0].product_title, "Sample Phone")
        self.assertEqual(rows[0].review_rating, "5.0")

    def test_normalize_review_rows_zero_max_means_uncapped(self) -> None:
        """A zero max review value should not cap normalized review rows."""

        product = ProductInput(
            category="Electronics",
            subcategory="Smartphones",
            product_title="Sample Phone",
            product_price="₹12,999",
            product_listing_rating="4.3",
            product_ratings_count="1,234",
            product_reviews_count="56",
            product_url="https://www.flipkart.com/sample/p/itm?pid=MOB123",
            product_id="MOB123",
            source_url="https://www.flipkart.com/search?q=Smartphones",
            source_csv="electronics-smartphones.csv",
        )
        raw_reviews = [
            {
                "rating": 5.0,
                "title": f"Title {index}",
                "body": "Body",
                "reviewer": "Reviewer",
                "date": "1 day ago",
                "helpful_count": 1,
            }
            for index in range(3)
        ]

        rows = normalize_review_rows(product, raw_reviews, max_reviews=0)

        self.assertEqual(len(rows), 3)

    def test_write_review_artifacts_creates_reports_and_zip(self) -> None:
        """Review artifacts should include per-subcategory CSVs, combined CSV, reports, and ZIP."""

        with TemporaryDirectory() as temp_dir_name:
            output_dir = Path(temp_dir_name)
            row = ReviewRow(
                category="Electronics",
                subcategory="Smartphones",
                product_title="Sample Phone",
                product_price="₹12,999",
                product_listing_rating="4.3",
                product_ratings_count="1,234",
                product_reviews_count="56",
                product_url="https://www.flipkart.com/sample/p/itm?pid=MOB123",
                product_id="MOB123",
                source_url="https://www.flipkart.com/search?q=Smartphones",
                review_rating="5.0",
                review_title="Good",
                review_body="Nice",
                reviewer="Rajiv",
                review_date="1 day ago",
                helpful_count="2",
                variant="Blue",
                city="Delhi",
                reviewer_badge="Gold Reviewer",
            )
            result = ProductReviewResult(
                product=ProductInput(
                    category="Electronics",
                    subcategory="Smartphones",
                    product_title="Sample Phone",
                    product_price="₹12,999",
                    product_listing_rating="4.3",
                    product_ratings_count="1,234",
                    product_reviews_count="56",
                    product_url="https://www.flipkart.com/sample/p/itm?pid=MOB123",
                    product_id="MOB123",
                    source_url="https://www.flipkart.com/search?q=Smartphones",
                    source_csv="electronics-smartphones.csv",
                ),
                status="success",
                review_count=1,
                error="",
            )

            zip_path = write_review_artifacts(
                output_dir,
                [row],
                [result],
                {"max_reviews": 0, "uncapped": True},
            )

            combined_csv = output_dir / "combined_reviews.csv"
            report = json.loads((output_dir / "review_run_report.json").read_text())
            with combined_csv.open(newline="", encoding="utf-8") as csv_file:
                rows = list(csv.DictReader(csv_file))

            self.assertEqual(rows[0]["review_title"], "Good")
            self.assertEqual(report["summary"]["products_attempted"], 1)
            self.assertTrue(report["scrape_config"]["uncapped"])
            self.assertEqual(report["summary"]["total_reviews_collected"], 1)
            self.assertTrue((output_dir / "electronics-smartphones-reviews.csv").exists())
            self.assertTrue((output_dir / "empty_products.csv").exists())
            self.assertTrue((output_dir / "failed_products.csv").exists())
            self.assertTrue((output_dir / "scrape_config.json").exists())
            with zipfile.ZipFile(zip_path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("combined_reviews.csv", archive.namelist())
                self.assertIn("review_run_report.json", archive.namelist())
                self.assertIn("scrape_config.json", archive.namelist())

    def test_append_product_artifacts_persists_incremental_progress(self) -> None:
        """Each completed product should be written to disk immediately."""

        with TemporaryDirectory() as temp_dir_name:
            output_dir = Path(temp_dir_name)
            product = ProductInput(
                category="Electronics",
                subcategory="Smartphones",
                product_title="Sample Phone",
                product_price="₹12,999",
                product_listing_rating="4.3",
                product_ratings_count="1,234",
                product_reviews_count="56",
                product_url="https://www.flipkart.com/sample/p/itm?pid=MOB123",
                product_id="MOB123",
                source_url="https://www.flipkart.com/search?q=Smartphones",
                source_csv="electronics-smartphones.csv",
            )
            payload = type("Payload", (), {})()
            payload.rows = [
                ReviewRow(
                    category="Electronics",
                    subcategory="Smartphones",
                    product_title="Sample Phone",
                    product_price="₹12,999",
                    product_listing_rating="4.3",
                    product_ratings_count="1,234",
                    product_reviews_count="56",
                    product_url="https://www.flipkart.com/sample/p/itm?pid=MOB123",
                    product_id="MOB123",
                    source_url="https://www.flipkart.com/search?q=Smartphones",
                    review_rating="5.0",
                    review_title="Good",
                    review_body="Nice",
                    reviewer="Rajiv",
                    review_date="1 day ago",
                    helpful_count="2",
                    variant="Blue",
                    city="Delhi",
                    reviewer_badge="Gold Reviewer",
                ),
            ]
            payload.result = ProductReviewResult(
                product=product,
                status="success",
                review_count=1,
                error="",
            )

            append_product_artifacts(output_dir, payload)

            self.assertTrue((output_dir / "combined_reviews.csv").exists())
            self.assertTrue((output_dir / "electronics-smartphones-reviews.csv").exists())
            self.assertEqual(load_completed_product_keys(output_dir), {"MOB123"})

    def test_run_review_batch_resume_skips_completed_products(self) -> None:
        """Resume mode should skip products already present in the status ledger."""

        with TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            product_dir = temp_dir / "products"
            output_dir = temp_dir / "reviews"
            product_dir.mkdir()
            output_dir.mkdir()

            csv_path = product_dir / "electronics-smartphones.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
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
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "category": "Electronics",
                        "subcategory": "Smartphones",
                        "title": "Done Phone",
                        "price": "₹10,000",
                        "rating": "4.1",
                        "ratings_count": "100",
                        "reviews_count": "10",
                        "product_url": "https://www.flipkart.com/sample/p/itm?pid=MOBDONE",
                        "product_id": "MOBDONE",
                        "source_url": "https://www.flipkart.com/search?q=Smartphones",
                    },
                )
            with (output_dir / "product_review_status.csv").open(
                "w",
                newline="",
                encoding="utf-8",
            ) as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=[
                    "category",
                    "subcategory",
                    "product_title",
                    "product_url",
                    "product_id",
                    "status",
                    "review_count",
                    "error",
                ])
                writer.writeheader()
                writer.writerow(
                    {
                        "category": "Electronics",
                        "subcategory": "Smartphones",
                        "product_title": "Done Phone",
                        "product_url": "https://www.flipkart.com/sample/p/itm?pid=MOBDONE",
                        "product_id": "MOBDONE",
                        "status": "success",
                        "review_count": "10",
                        "error": "",
                    },
                )

            rows, results = run_review_batch(
                product_dir=product_dir,
                output_dir=output_dir,
                max_reviews=0,
                concurrency=1,
                retry_count=0,
                resume=True,
            )

            self.assertEqual(len(rows), 0)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].product.product_id, "MOBDONE")

    def test_parse_args_accepts_serial_wait_options(self) -> None:
        """CLI options should allow conservative serial review scraping waits."""

        args = parse_args(
            [
                "--product-dir",
                "products",
                "--output-dir",
                "reviews",
                "--concurrency",
                "1",
                "--wait-seconds",
                "8",
                "--empty-retry-wait-seconds",
                "12",
                "--page-delay-seconds",
                "2",
                "--product-delay-seconds",
                "5",
            ],
        )

        self.assertEqual(args.concurrency, 1)
        self.assertEqual(args.wait_seconds, 8)
        self.assertEqual(args.empty_retry_wait_seconds, 12)
        self.assertEqual(args.page_delay_seconds, 2)
        self.assertEqual(args.product_delay_seconds, 5)
        self.assertFalse(args.no_resume)


if __name__ == "__main__":
    unittest.main()
