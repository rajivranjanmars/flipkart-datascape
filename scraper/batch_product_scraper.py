"""Batch product listing scraper for the requested Flipkart subcategories."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, urlparse

from bs4 import BeautifulSoup, Tag

from scraper.utils import create_browser_context, get_page_html

BASE_URL = "https://www.flipkart.com"
DEFAULT_MAX_PRODUCTS = 100
DEFAULT_CONCURRENCY = 4
MAX_EMPTY_PAGES = 3
MAX_PAGES_PER_SUBCATEGORY = 12
CSV_FIELDS = [
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
PRICE_PATTERN = re.compile(r"₹\s*[\d,]+")
RATING_PATTERN = re.compile(r"(?<!\d)([1-5]\.\d)(?!\d)")
RATING_WITH_COUNTS_PATTERN = re.compile(
    r"(?<!\d)([1-5]\.\d)(?!\d).{0,40}?[\d,]+\s+Ratings?",
    re.IGNORECASE,
)
RATINGS_COUNT_PATTERN = re.compile(r"([\d,]+)\s+Ratings?", re.IGNORECASE)
REVIEWS_COUNT_PATTERN = re.compile(r"([\d,]+)\s+Reviews?", re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r"\s+")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class SubcategoryTarget:
    """A category/subcategory pair to scrape from Flipkart."""

    category: str
    subcategory: str


@dataclass(frozen=True)
class ProductRecord:
    """A normalized product listing row written to each category CSV."""

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


@dataclass(frozen=True)
class RunResult:
    """Summary of one subcategory scrape attempt."""

    category: str
    subcategory: str
    search_url: str
    csv_path: Path
    row_count: int
    status: str
    error: str


SUBCATEGORY_TARGETS: list[SubcategoryTarget] = [
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


def slugify(value: str) -> str:
    """Return a lowercase ASCII-ish slug safe for generated filenames."""

    slug = SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "unknown"


def build_search_url(query: str) -> str:
    """Return a Flipkart search URL for a subcategory query."""

    return f"{BASE_URL}/search?q={quote_plus(query)}"


def normalize_text(value: str) -> str:
    """Collapse whitespace in scraped text."""

    return WHITESPACE_PATTERN.sub(" ", value).strip()


def absolute_product_url(href: str) -> str:
    """Return an absolute Flipkart product URL without page fragments."""

    normalized_href = href.split("#", maxsplit=1)[0]

    if normalized_href.startswith("http"):
        return normalized_href

    return f"{BASE_URL}{normalized_href}"


def extract_product_id(product_url: str) -> str:
    """Return the product identifier from a Flipkart product URL when present."""

    parsed_url = urlparse(product_url)
    query_params = parse_qs(parsed_url.query)

    if "pid" in query_params and query_params["pid"]:
        return query_params["pid"][0]

    path_parts = [part for part in parsed_url.path.split("/") if part]
    if "p" in path_parts:
        p_index = path_parts.index("p")
        if p_index + 1 < len(path_parts):
            return path_parts[p_index + 1]

    return ""


def find_card_container(anchor: Tag) -> Tag:
    """Return the nearest useful listing-card container for a product anchor."""

    current: Tag = anchor
    best: Tag = anchor

    for _ in range(5):
        parent = current.parent

        if not isinstance(parent, Tag):
            break

        candidate_text = normalize_text(parent.get_text(" ", strip=True))
        if PRICE_PATTERN.search(candidate_text) is not None:
            best = parent
            break

        best = parent
        current = parent

    return best


def extract_title_from_url(product_url: str) -> str:
    """Return a readable product title from the URL slug."""

    parsed_url = urlparse(product_url)
    path_parts = [part for part in parsed_url.path.split("/") if part]

    if not path_parts:
        return ""

    slug = path_parts[0]
    return normalize_text(slug.replace("-", " "))


def is_noisy_title_candidate(candidate: str, slug_title: str) -> bool:
    """Return whether scraped text is less useful than the URL slug title."""

    normalized_candidate = normalize_text(candidate)

    if not normalized_candidate:
        return True

    lower_candidate = normalized_candidate.lower()
    if lower_candidate.startswith("add to compare"):
        return True

    if lower_candidate in {"off on exchange", "bank offer"}:
        return True

    if "ratings" in lower_candidate or "reviews" in lower_candidate:
        return True

    if RATING_PATTERN.fullmatch(normalized_candidate.split(" ", maxsplit=1)[0]):
        return True

    if PRICE_PATTERN.search(normalized_candidate) is not None:
        return True

    if len(normalized_candidate) > 140:
        return True

    if slug_title and len(normalized_candidate) < 12:
        return True

    if slug_title and " strap" in lower_candidate:
        return True

    return False


def extract_title(anchor: Tag, card: Tag, product_url: str) -> str:
    """Return the best available title text from a listing anchor/card."""

    slug_title = extract_title_from_url(product_url)
    title_candidates = [
        anchor.get("title", ""),
        anchor.get_text(" ", strip=True),
    ]

    for node in card.find_all(["div", "span"], recursive=True):
        if not isinstance(node, Tag):
            continue

        text = normalize_text(node.get_text(" ", strip=True))
        if text and PRICE_PATTERN.search(text) is None:
            title_candidates.append(text)

    for candidate in title_candidates:
        title = normalize_text(str(candidate))
        if title and "/p/" not in title and not is_noisy_title_candidate(title, slug_title):
            return title

    return slug_title or "Unknown product"


def extract_counts(card_text: str) -> tuple[str, str]:
    """Return ratings and reviews counts from card text when visible."""

    ratings_match = RATINGS_COUNT_PATTERN.search(card_text)
    reviews_match = REVIEWS_COUNT_PATTERN.search(card_text)
    ratings_count = ratings_match.group(1) if ratings_match is not None else ""
    reviews_count = reviews_match.group(1) if reviews_match is not None else ""
    return ratings_count, reviews_count


def extract_rating(card_text: str) -> str:
    """Return the visible product rating while avoiding model numbers like 5G."""

    rating_with_counts_match = RATING_WITH_COUNTS_PATTERN.search(card_text)
    if rating_with_counts_match is not None:
        return rating_with_counts_match.group(1)

    return ""


def parse_product_records(
    html: str,
    category: str,
    subcategory: str,
    source_url: str,
    max_records: int,
) -> list[ProductRecord]:
    """Extract unique product records from one Flipkart listing page."""

    soup = BeautifulSoup(html, "lxml")
    records: list[ProductRecord] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue

        href = str(anchor["href"]).strip()
        if "/p/" not in href:
            continue

        product_url = absolute_product_url(href)
        if product_url in seen_urls:
            continue

        seen_urls.add(product_url)
        card = find_card_container(anchor)
        card_text = normalize_text(card.get_text(" ", strip=True))
        price_match = PRICE_PATTERN.search(card_text)
        ratings_count, reviews_count = extract_counts(card_text)
        records.append(
            ProductRecord(
                category=category,
                subcategory=subcategory,
                title=extract_title(anchor, card, product_url),
                price=price_match.group(0) if price_match is not None else "",
                rating=extract_rating(card_text),
                ratings_count=ratings_count,
                reviews_count=reviews_count,
                product_url=product_url,
                product_id=extract_product_id(product_url),
                source_url=source_url,
            ),
        )

        if len(records) >= max_records:
            break

    return records


def build_page_url(search_url: str, page_number: int) -> str:
    """Return a paginated Flipkart search URL."""

    separator = "&" if "?" in search_url else "?"
    return f"{search_url}{separator}page={page_number}"


def collect_products_for_target(
    target: SubcategoryTarget,
    max_products: int,
    retry_count: int,
) -> list[ProductRecord]:
    """Collect up to max_products product rows for one target using Playwright."""

    browser = None
    context = None
    records: list[ProductRecord] = []
    seen_urls: set[str] = set()
    search_url = build_search_url(target.subcategory)
    empty_pages = 0

    try:
        browser, context = create_browser_context()

        for page_number in range(1, MAX_PAGES_PER_SUBCATEGORY + 1):
            page_url = build_page_url(search_url, page_number)
            html = None

            for attempt in range(retry_count + 1):
                html = get_page_html(context, page_url)
                if html is not None:
                    break

                time.sleep(2 + attempt)

            if html is None:
                empty_pages += 1
                if empty_pages >= MAX_EMPTY_PAGES:
                    break
                continue

            page_records = parse_product_records(
                html,
                target.category,
                target.subcategory,
                page_url,
                max_products - len(records),
            )

            new_records = [
                record for record in page_records if record.product_url not in seen_urls
            ]

            if not new_records:
                empty_pages += 1
                if empty_pages >= MAX_EMPTY_PAGES:
                    break
                continue

            empty_pages = 0
            for record in new_records:
                seen_urls.add(record.product_url)
                records.append(record)

                if len(records) >= max_products:
                    break

            if len(records) >= max_products:
                break

    finally:
        if context is not None:
            context.close()
        if browser is not None:
            browser.close()

    return records[:max_products]


def write_category_csv(
    output_dir: Path,
    category: str,
    subcategory: str,
    records: Iterable[ProductRecord],
) -> Path:
    """Write one CSV for a category/subcategory and return its path."""

    csv_path = output_dir / f"{slugify(category + '__' + subcategory)}.csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))

    return csv_path


def scrape_and_write_target(
    target: SubcategoryTarget,
    output_dir: Path,
    max_products: int,
    retry_count: int,
) -> RunResult:
    """Scrape one target, write its CSV, and return a run result."""

    search_url = build_search_url(target.subcategory)

    try:
        records = collect_products_for_target(target, max_products, retry_count)
        csv_path = write_category_csv(output_dir, target.category, target.subcategory, records)
        status = "success" if records else "empty"
        error = "" if records else "No products parsed from Flipkart listing pages."
        return RunResult(
            category=target.category,
            subcategory=target.subcategory,
            search_url=search_url,
            csv_path=csv_path,
            row_count=len(records),
            status=status,
            error=error,
        )
    except Exception as exc:
        csv_path = write_category_csv(output_dir, target.category, target.subcategory, [])
        return RunResult(
            category=target.category,
            subcategory=target.subcategory,
            search_url=search_url,
            csv_path=csv_path,
            row_count=0,
            status="failed",
            error=str(exc),
        )


def result_to_json(result: RunResult, output_dir: Path) -> dict[str, object]:
    """Return a JSON-serializable representation of a run result."""

    return {
        "category": result.category,
        "subcategory": result.subcategory,
        "search_url": result.search_url,
        "csv_path": result.csv_path.relative_to(output_dir).as_posix(),
        "row_count": result.row_count,
        "status": result.status,
        "error": result.error,
    }


def write_run_artifacts(output_dir: Path, results: list[RunResult]) -> Path:
    """Write run reports and a ZIP containing CSVs plus reports."""

    successful_results = [result for result in results if result.status == "success"]
    report = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "summary": {
            "total_subcategories": len(results),
            "successful_subcategories": len(successful_results),
            "empty_subcategories": len(
                [result for result in results if result.status == "empty"]
            ),
            "failed_subcategories": len(
                [result for result in results if result.status == "failed"]
            ),
            "total_rows": sum(result.row_count for result in results),
        },
        "results": [result_to_json(result, output_dir) for result in results],
    }
    json_report_path = output_dir / "run_report.json"
    text_report_path = output_dir / "run_report.txt"
    zip_path = output_dir / "flipkart_product_csvs.zip"

    json_report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    text_lines = [
        "Flipkart product scrape run report",
        f"Generated at: {report['generated_at']}",
        f"Total subcategories: {report['summary']['total_subcategories']}",
        f"Successful subcategories: {report['summary']['successful_subcategories']}",
        f"Empty subcategories: {report['summary']['empty_subcategories']}",
        f"Failed subcategories: {report['summary']['failed_subcategories']}",
        f"Total rows: {report['summary']['total_rows']}",
        "",
    ]
    for result in results:
        text_lines.append(
            f"{result.status.upper()}: {result.category} / {result.subcategory} "
            f"rows={result.row_count} csv={result.csv_path.name} error={result.error}",
        )
    text_report_path.write_text("\n".join(text_lines) + "\n", encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for result in results:
            archive.write(result.csv_path, arcname=result.csv_path.name)
        archive.write(json_report_path, arcname=json_report_path.name)
        archive.write(text_report_path, arcname=text_report_path.name)

    return zip_path


def run_batch(
    output_dir: Path,
    max_products: int,
    concurrency: int,
    retry_count: int,
) -> list[RunResult]:
    """Run all subcategory scrapes with bounded process-level parallelism."""

    output_dir.mkdir(parents=True, exist_ok=True)
    ordered_results: dict[str, RunResult] = {}
    concurrency = max(1, min(concurrency, len(SUBCATEGORY_TARGETS)))

    with ProcessPoolExecutor(max_workers=concurrency) as executor:
        future_map = {
            executor.submit(
                scrape_and_write_target,
                target,
                output_dir,
                max_products,
                retry_count,
            ): target
            for target in SUBCATEGORY_TARGETS
        }

        for future in as_completed(future_map):
            target = future_map[future]
            result = future.result()
            ordered_results[f"{target.category}/{target.subcategory}"] = result
            print(
                f"{result.status.upper()}: {target.category} / {target.subcategory} "
                f"rows={result.row_count}",
                flush=True,
            )

    return [
        ordered_results[f"{target.category}/{target.subcategory}"]
        for target in SUBCATEGORY_TARGETS
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the batch product scraper."""

    parser = argparse.ArgumentParser(
        description="Scrape Flipkart product listings for the requested subcategories.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-products", type=int, default=DEFAULT_MAX_PRODUCTS)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--retries", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the batch scraper from the command line."""

    args = parse_args(argv)
    results = run_batch(
        output_dir=args.output_dir,
        max_products=args.max_products,
        concurrency=args.concurrency,
        retry_count=args.retries,
    )
    zip_path = write_run_artifacts(args.output_dir, results)
    print(f"ZIP written: {zip_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
