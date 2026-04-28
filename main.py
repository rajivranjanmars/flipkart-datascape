"""CLI entrypoint for orchestrating Flipkart product review scraping."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import pandas
import tqdm

from scraper.product_list import get_product_urls
from scraper.review_scraper import scrape_reviews
from scraper.utils import create_browser_context

REVIEW_COLUMNS: list[str] = [
    "product_url",
    "product_name",
    "rating",
    "title",
    "body",
    "reviewer",
    "date",
    "helpful_count",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape product reviews from a Flipkart category or listing URL.",
    )
    parser.add_argument("category_url", help="The Flipkart category or listing URL to scrape.")
    parser.add_argument("--max-products", default=100, type=int)
    parser.add_argument("--output-dir", default="data", type=str)
    parser.add_argument("--format", choices=["csv", "json", "both"], default="csv")
    parser.add_argument("--product-name-prefix", default="", type=str)
    return parser.parse_args(argv)


def extract_product_name(product_url: str, product_name_prefix: str = "") -> str:
    normalized_url = product_url.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if "flipkart.com/" in normalized_url:
        path_after_domain = normalized_url.split("flipkart.com/", maxsplit=1)[1]
    else:
        url_without_scheme = normalized_url.split("://", maxsplit=1)[-1]
        path_after_domain = (
            url_without_scheme.split("/", maxsplit=1)[1]
            if "/" in url_without_scheme
            else ""
        )
    product_slug = path_after_domain.split("/", maxsplit=1)[0].strip("/-") or "unknown-product"
    if product_name_prefix:
        return f"{product_name_prefix}{product_slug}"
    return product_slug


def append_product_reviews(product_reviews: list[dict], output_path: Path) -> None:
    """Append reviews for one product to the output CSV immediately after scraping."""
    if not product_reviews:
        return
    df = pandas.DataFrame(product_reviews, columns=REVIEW_COLUMNS)
    write_header = not output_path.exists()
    df.to_csv(
        os.fspath(output_path),
        mode="a",
        header=write_header,
        index=False,
        encoding="utf-8",
    )


def print_final_summary(
    total_products_scraped: int,
    total_reviews_collected: int,
    output_path: Path,
) -> None:
    print(f"Total products scraped: {total_products_scraped}")
    print(f"Total reviews collected: {total_reviews_collected}")
    print(f"File saved to path: {os.fspath(output_path)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"reviews_{timestamp}.csv"

    master_reviews: list[dict] = []
    completed_products = 0
    browser = None
    context = None

    print("Flipkart Review Scraper - Starting...")
    print(f"Configured to scrape up to {args.max_products} products.")
    print(f"Saving incrementally to: {output_path}")

    try:
        browser, context = create_browser_context()
        product_urls = get_product_urls(args.category_url, context, args.max_products)
        print(f"Found {len(product_urls)} product URLs.")

        total_products = len(product_urls)

        with tqdm.tqdm(product_urls, total=total_products, unit="product") as product_progress:
            for index, product_url in enumerate(product_progress, start=1):
                product_progress.set_description(
                    f"Scraping product {index} of {total_products}",
                )
                product_name = extract_product_name(product_url, args.product_name_prefix)
                product_reviews = scrape_reviews(product_url, context, product_name)

                # Save to disk immediately — data is safe even if process is killed after this
                append_product_reviews(product_reviews, output_path)

                master_reviews.extend(product_reviews)
                completed_products += 1

                tqdm.tqdm.write(
                    f"Product {index}/{total_products}: {product_name} | Reviews: {len(product_reviews)} | Total saved: {len(master_reviews)}",
                )

    except KeyboardInterrupt:
        print("\nInterrupted. All completed products already saved to disk.")
        print_final_summary(completed_products, len(master_reviews), output_path)
        return 130
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

    print_final_summary(completed_products, len(master_reviews), output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
