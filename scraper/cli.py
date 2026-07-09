"""Flag-based CLI for scripting and automation.

With no arguments this launches the interactive app. With arguments it runs a
single operation non-interactively (handy for cron, CI, or piping). Both paths
share :mod:`scraper.runner`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scraper.runner import get_profile, run_pipeline, run_products, run_reviews, run_search
from scraper.sites.registry import all_adapters, available_sites, get_adapter

_PROFILE_CHOICES = ["fast", "balanced", "polite"]


def _add_site(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--site",
        required=True,
        choices=available_sites(),
        help="Marketplace to scrape.",
    )
    parser.add_argument(
        "--profile",
        default="balanced",
        choices=_PROFILE_CHOICES,
        help="Speed/politeness profile (default: balanced).",
    )
    parser.add_argument(
        "--cookies",
        type=Path,
        default=None,
        help="Path to a cookies JSON file (browser-export or Playwright format) "
        "for a logged-in session. Defaults to secrets/<site>_cookies.json if present.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scraper",
        description="Multi-marketplace scraper (Flipkart, Amazon, Myntra, Meesho). "
        "Run with no arguments for the interactive app.",
    )
    parser.add_argument("--list-sites", action="store_true", help="List supported sites and exit.")
    sub = parser.add_subparsers(dest="command")

    products = sub.add_parser("products", help="Scrape preset category listings.")
    _add_site(products)
    products.add_argument("--output-dir", type=Path, required=True)
    products.add_argument("--max-products", type=int, default=100)
    products.add_argument("--concurrency", type=int, default=0, help="0 = use profile default.")
    products.add_argument("--retries", type=int, default=2)

    search = sub.add_parser("search", help="Scrape a single query or listing URL.")
    _add_site(search)
    search.add_argument("query", help="Free-text query, or a full listing URL.")
    search.add_argument("--output-dir", type=Path, required=True)
    search.add_argument("--max-products", type=int, default=100)
    search.add_argument("--retries", type=int, default=2)

    reviews = sub.add_parser("reviews", help="Scrape reviews from a product folder (resumable).")
    _add_site(reviews)
    reviews.add_argument("--product-dir", type=Path, required=True)
    reviews.add_argument("--output-dir", type=Path, required=True)
    reviews.add_argument("--max-reviews", type=int, default=100, help="0 = uncapped.")
    reviews.add_argument("--concurrency", type=int, default=0, help="0 = use profile default.")
    reviews.add_argument("--retries", type=int, default=2)
    reviews.add_argument("--no-resume", action="store_true")
    reviews.add_argument(
        "--product-delay",
        type=float,
        default=0.0,
        help="Seconds to pause between products (per worker). Use with low "
        "concurrency to back off a site that is throttling review pages.",
    )

    pipeline = sub.add_parser("pipeline", help="Products then reviews end-to-end.")
    _add_site(pipeline)
    pipeline.add_argument("--output-dir", type=Path, required=True)
    pipeline.add_argument("--max-products", type=int, default=50)
    pipeline.add_argument("--max-reviews", type=int, default=50)
    pipeline.add_argument("--retries", type=int, default=2)
    pipeline.add_argument(
        "--product-delay",
        type=float,
        default=0.0,
        help="Seconds to pause between products during the review step (per worker).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    import sys

    raw_args = sys.argv[1:] if argv is None else argv

    # No arguments → interactive app.
    if not raw_args:
        from scraper.app import run_app

        return run_app()

    parser = build_parser()
    args = parser.parse_args(raw_args)

    if args.list_sites:
        for adapter in all_adapters():
            caps = "products + reviews" if adapter.supports_reviews else "products only"
            print(f"{adapter.name:9s} {adapter.label:10s} [{caps}]")
        return 0

    if args.command is None:
        parser.print_help()
        return 1

    adapter = get_adapter(args.site)
    profile = get_profile(args.profile)

    cookies = None
    if args.cookies is not None:
        from scraper.core.cookies import load_cookies

        cookies = load_cookies(args.cookies)

    if args.command == "products":
        concurrency = args.concurrency or profile.default_concurrency
        run_products(
            adapter,
            output_dir=args.output_dir,
            max_products=args.max_products,
            concurrency=concurrency,
            retries=args.retries,
            profile=profile,
            cookies=cookies,
        )
    elif args.command == "search":
        listing_url = args.query if args.query.startswith("http") else None
        run_search(
            adapter,
            query="" if listing_url else args.query,
            listing_url=listing_url,
            output_dir=args.output_dir,
            max_products=args.max_products,
            retries=args.retries,
            profile=profile,
            cookies=cookies,
        )
    elif args.command == "reviews":
        if not adapter.supports_reviews:
            print(f"{adapter.label} does not support review scraping.")
            return 2
        concurrency = args.concurrency or profile.default_concurrency
        run_reviews(
            adapter,
            product_dir=args.product_dir,
            output_dir=args.output_dir,
            max_reviews=args.max_reviews,
            concurrency=concurrency,
            retries=args.retries,
            resume=not args.no_resume,
            product_delay_seconds=args.product_delay,
            profile=profile,
            cookies=cookies,
        )
    elif args.command == "pipeline":
        run_pipeline(
            adapter,
            output_dir=args.output_dir,
            max_products=args.max_products,
            max_reviews=args.max_reviews,
            retries=args.retries,
            product_delay_seconds=args.product_delay,
            profile=profile,
            cookies=cookies,
        )

    return 0
