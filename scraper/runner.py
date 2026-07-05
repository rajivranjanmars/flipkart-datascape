"""High-level operations shared by the interactive app and the flag-based CLI.

Everything the user can "do" funnels through here so both front-ends behave
identically. A :class:`SpeedProfile` bundles the knobs that trade speed for
politeness.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scraper.core.batch import (
    Logger,
    default_logger,
    run_product_batch,
    run_review_batch,
)
from scraper.core.browser import BrowserSession
from scraper.core.cookies import discover_cookies
from scraper.core.engine import collect_product_urls, collect_products
from scraper.core.models import PRODUCT_CSV_FIELDS, SubcategoryTarget
from scraper.core.textutils import slugify
from scraper.sites.base import SiteAdapter


def _resolve_cookies(
    adapter: SiteAdapter,
    cookies: list[dict] | None,
    logger,
) -> list[dict] | None:
    """Use explicit cookies, else auto-load secrets/<site>_cookies.json."""

    if cookies is None:
        cookies = discover_cookies(adapter.name)
    if cookies:
        logger(f"Using {len(cookies)} auth cookie(s) for {adapter.label} (logged-in session).")
    return cookies


@dataclass(frozen=True)
class SpeedProfile:
    """Bundle of speed-vs-politeness knobs."""

    name: str
    block_resources: bool
    settle_ms: int
    default_concurrency: int
    page_delay_seconds: float
    description: str


SPEED_PROFILES: dict[str, SpeedProfile] = {
    "fast": SpeedProfile(
        name="fast",
        block_resources=True,
        settle_ms=300,
        default_concurrency=8,
        page_delay_seconds=0.0,
        description="Block images/css, minimal waits, high concurrency. Fastest.",
    ),
    "balanced": SpeedProfile(
        name="balanced",
        block_resources=True,
        settle_ms=650,
        default_concurrency=4,
        page_delay_seconds=0.0,
        description="Block images/css, moderate waits. Good default.",
    ),
    "polite": SpeedProfile(
        name="polite",
        block_resources=False,
        settle_ms=1300,
        default_concurrency=2,
        page_delay_seconds=1.0,
        description="Load everything, longer waits, low concurrency. Gentlest on the site.",
    ),
}

DEFAULT_PROFILE = "balanced"


def get_profile(name: str) -> SpeedProfile:
    return SPEED_PROFILES.get(name, SPEED_PROFILES[DEFAULT_PROFILE])


# --------------------------------------------------------------------------- #
# Operations
# --------------------------------------------------------------------------- #
def run_products(
    adapter: SiteAdapter,
    *,
    output_dir: Path,
    targets: list[SubcategoryTarget] | None = None,
    max_products: int = 100,
    concurrency: int = 4,
    retries: int = 2,
    profile: SpeedProfile | None = None,
    cookies: list[dict] | None = None,
    logger: Logger = default_logger,
) -> list[dict[str, object]]:
    """Scrape the default (or given) category targets for a site."""

    profile = profile or get_profile(DEFAULT_PROFILE)
    cookies = _resolve_cookies(adapter, cookies, logger)
    return run_product_batch(
        adapter,
        output_dir=output_dir,
        targets=targets,
        max_products=max_products,
        concurrency=concurrency,
        retries=retries,
        settle_ms=profile.settle_ms,
        block_resources=profile.block_resources,
        cookies=cookies,
        logger=logger,
    )


def run_search(
    adapter: SiteAdapter,
    *,
    query: str,
    output_dir: Path,
    category: str = "",
    subcategory: str = "",
    max_products: int = 100,
    retries: int = 2,
    profile: SpeedProfile | None = None,
    cookies: list[dict] | None = None,
    logger: Logger = default_logger,
    listing_url: str | None = None,
) -> Path:
    """Scrape a single free-text query (or explicit listing URL) into one CSV."""

    from dataclasses import asdict
    import csv

    from scraper.core.batch import build_session_kwargs

    profile = profile or get_profile(DEFAULT_PROFILE)
    cookies = _resolve_cookies(adapter, cookies, logger)
    output_dir.mkdir(parents=True, exist_ok=True)
    session_kwargs = build_session_kwargs(adapter, profile.block_resources, cookies)

    label = listing_url or query
    logger(f"Searching {adapter.label} for: {label!r} (max {max_products})")
    with BrowserSession(**session_kwargs) as session:  # type: ignore[arg-type]
        if listing_url:
            records = collect_product_urls(
                adapter,
                listing_url=listing_url,
                session=session,
                max_products=max_products,
                retries=retries,
                settle_ms=profile.settle_ms,
            )
        else:
            records = collect_products(
                adapter,
                category=category or "Search",
                subcategory=subcategory or query,
                query=query,
                session=session,
                max_products=max_products,
                retries=retries,
                settle_ms=profile.settle_ms,
            )

    slug = slugify(query or listing_url or "results")
    csv_path = output_dir / f"{adapter.name}-search-{slug}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRODUCT_CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    logger(f"Wrote {len(records)} products to {csv_path}")
    return csv_path


def run_reviews(
    adapter: SiteAdapter,
    *,
    product_dir: Path,
    output_dir: Path,
    max_reviews: int = 100,
    concurrency: int = 8,
    retries: int = 2,
    resume: bool = True,
    profile: SpeedProfile | None = None,
    cookies: list[dict] | None = None,
    logger: Logger = default_logger,
) -> dict[str, object]:
    """Scrape reviews for every product CSV in ``product_dir`` (resumable)."""

    profile = profile or get_profile(DEFAULT_PROFILE)
    cookies = _resolve_cookies(adapter, cookies, logger)
    return run_review_batch(
        adapter,
        product_dir=product_dir,
        output_dir=output_dir,
        max_reviews=max_reviews,
        concurrency=concurrency,
        retries=retries,
        settle_ms=profile.settle_ms,
        page_delay_seconds=profile.page_delay_seconds,
        resume=resume,
        block_resources=profile.block_resources,
        cookies=cookies,
        logger=logger,
    )


def run_pipeline(
    adapter: SiteAdapter,
    *,
    output_dir: Path,
    targets: list[SubcategoryTarget] | None = None,
    max_products: int = 50,
    max_reviews: int = 50,
    product_concurrency: int = 4,
    review_concurrency: int = 8,
    retries: int = 2,
    profile: SpeedProfile | None = None,
    cookies: list[dict] | None = None,
    logger: Logger = default_logger,
) -> dict[str, object]:
    """Run products then reviews into ``output_dir/products`` and ``.../reviews``."""

    profile = profile or get_profile(DEFAULT_PROFILE)
    cookies = _resolve_cookies(adapter, cookies, logger)
    product_dir = output_dir / "products"
    review_dir = output_dir / "reviews"

    logger("Pipeline step 1/2: product listings")
    product_results = run_products(
        adapter,
        output_dir=product_dir,
        targets=targets,
        max_products=max_products,
        concurrency=product_concurrency,
        retries=retries,
        profile=profile,
        cookies=cookies,
        logger=logger,
    )

    if not adapter.supports_reviews:
        logger(f"{adapter.label} does not support reviews; pipeline stops after products.")
        return {"products": product_results, "reviews": None}

    logger("Pipeline step 2/2: reviews")
    review_report = run_reviews(
        adapter,
        product_dir=product_dir,
        output_dir=review_dir,
        max_reviews=max_reviews,
        concurrency=review_concurrency,
        retries=retries,
        profile=profile,
        cookies=cookies,
        logger=logger,
    )
    return {"products": product_results, "reviews": review_report}
