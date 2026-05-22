from __future__ import annotations

import csv
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from scraper.batch_product_scraper import (
    SUBCATEGORY_TARGETS,
    ProductRecord,
    RunResult,
    build_search_url,
    extract_title_from_url,
    parse_product_records,
    slugify,
    write_category_csv,
    write_run_artifacts,
)


class BatchProductScraperTests(unittest.TestCase):
    """Tests for the parallel Flipkart product scraping runner."""

    def test_target_list_contains_requested_subcategories_once(self) -> None:
        """The configured batch should include every requested subcategory once."""

        subcategory_names = [target.subcategory for target in SUBCATEGORY_TARGETS]

        self.assertEqual(len(subcategory_names), 18)
        self.assertEqual(len(set(subcategory_names)), 18)
        self.assertIn("Women Skincare", subcategory_names)
        self.assertIn("Smartwatches", subcategory_names)

    def test_build_search_url_encodes_subcategory_query(self) -> None:
        """Search URLs should be stable Flipkart search URLs for each subcategory."""

        self.assertEqual(
            build_search_url("Men Grooming"),
            "https://www.flipkart.com/search?q=Men+Grooming",
        )

    def test_slugify_creates_filesystem_safe_names(self) -> None:
        """Category labels should become predictable ASCII file stems."""

        self.assertEqual(
            slugify("Beauty & Care__Women Skincare"),
            "beauty-care-women-skincare",
        )

    def test_extract_title_from_url_returns_readable_slug_title(self) -> None:
        """URL slug fallback should produce readable product names."""

        self.assertEqual(
            extract_title_from_url(
                "https://www.flipkart.com/sample-phone-5g-blue/p/itm123?pid=MOB123",
            ),
            "sample phone 5g blue",
        )

    def test_parse_product_records_extracts_listing_card_data(self) -> None:
        """Product parser should extract product rows from listing-like HTML."""

        html = """
        <html>
          <body>
            <div class="card">
              <a href="/sample-phone/p/itm123?pid=MOB123">Sample Phone 5G</a>
              <div>Sample Phone 5G</div>
              <div>₹12,999</div>
              <div>4.3</div>
              <div>1,234 Ratings & 56 Reviews</div>
            </div>
            <div class="card">
              <a href="/sample-watch/p/itm456?pid=SMW456">Sample Watch</a>
              <span>₹2,499</span>
              <span>4.1</span>
            </div>
          </body>
        </html>
        """

        records = parse_product_records(
            html,
            category="Electronics",
            subcategory="Smartphones",
            source_url="https://www.flipkart.com/search?q=Smartphones",
            max_records=10,
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].title, "Sample Phone 5G")
        self.assertEqual(records[0].price, "₹12,999")
        self.assertEqual(records[0].rating, "4.3")
        self.assertEqual(records[0].ratings_count, "1,234")
        self.assertEqual(records[0].reviews_count, "56")
        self.assertEqual(records[0].product_id, "MOB123")
        self.assertTrue(records[0].product_url.startswith("https://www.flipkart.com/"))

    def test_write_csv_and_run_artifacts(self) -> None:
        """CSV, JSON report, text report, and ZIP should be generated together."""

        with TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            records = [
                ProductRecord(
                    category="Electronics",
                    subcategory="Smartphones",
                    title="Sample Phone",
                    price="₹12,999",
                    rating="4.3",
                    ratings_count="1,234",
                    reviews_count="56",
                    product_url="https://www.flipkart.com/sample-phone/p/itm123?pid=MOB123",
                    product_id="MOB123",
                    source_url="https://www.flipkart.com/search?q=Smartphones",
                ),
            ]
            csv_path = write_category_csv(temp_dir, "Electronics", "Smartphones", records)
            result = RunResult(
                category="Electronics",
                subcategory="Smartphones",
                search_url="https://www.flipkart.com/search?q=Smartphones",
                csv_path=csv_path,
                row_count=1,
                status="success",
                error="",
            )

            zip_path = write_run_artifacts(temp_dir, [result])

            with csv_path.open(newline="", encoding="utf-8") as csv_file:
                csv_rows = list(csv.DictReader(csv_file))
            report = json.loads((temp_dir / "run_report.json").read_text(encoding="utf-8"))

            self.assertEqual(csv_rows[0]["title"], "Sample Phone")
            self.assertEqual(report["summary"]["successful_subcategories"], 1)
            self.assertTrue((temp_dir / "run_report.txt").exists())
            self.assertTrue(zip_path.exists())
            with zipfile.ZipFile(zip_path) as archive:
                self.assertIn(csv_path.name, archive.namelist())
                self.assertIn("run_report.json", archive.namelist())


if __name__ == "__main__":
    unittest.main()
