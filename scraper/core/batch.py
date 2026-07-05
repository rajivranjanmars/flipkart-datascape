"""Generic batch orchestration: product listings and resumable reviews.

This module owns concurrency, resume state, reporting, and zipping. It runs
whatever :class:`~scraper.sites.base.SiteAdapter` it is handed. Batch workers
reuse one browser per process via :class:`~scraper.core.browser.BrowserSession`
instead of relaunching Chromium per item.
"""

from __future__ import annotations

import atexit
import csv
import datetime as dt
import json
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Iterable

from scraper.core.browser import BrowserSession
from scraper.core.engine import collect_products, scrape_product_reviews
from scraper.core.models import (
    PRODUCT_CSV_FIELDS,
    PRODUCT_STATUS_FIELDS,
    REVIEW_CSV_FIELDS,
    ProductRecord,
    SubcategoryTarget,
)
from scraper.core.proxy import resolve_proxy_from_env
from scraper.core.textutils import slugify
from scraper.sites.base import SiteAdapter

# Only success + genuine-empty are terminal. "failed" (network errors, anti-bot
# throttle) is intentionally retryable on resume so a throttled product gets
# another chance on the next pass.
STATUS_TERMINAL_STATES = {"success", "empty"}

Logger = Callable[[str], None]


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _format_elapsed(total_seconds: float) -> str:
    elapsed = max(0, int(total_seconds))
    days, remainder = divmod(elapsed, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def default_logger(message: str) -> None:
    """Print a timestamped progress line."""

    stamp = _utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{stamp}] {message}", flush=True)


# --------------------------------------------------------------------------- #
# CSV helpers
# --------------------------------------------------------------------------- #
def _write_rows(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _append_rows(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    rows_to_write = list(rows)
    if not rows_to_write:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows_to_write:
            writer.writerow(row)


# --------------------------------------------------------------------------- #
# Per-worker browser reuse (process pool)
# --------------------------------------------------------------------------- #
_WORKER: dict[str, object] = {}


def _init_worker(adapter: SiteAdapter, session_kwargs: dict[str, object]) -> None:
    _WORKER["adapter"] = adapter
    _WORKER["session_kwargs"] = session_kwargs
    _WORKER["session"] = None


def _worker_session() -> BrowserSession:
    session = _WORKER.get("session")
    if session is None:
        session = BrowserSession(**_WORKER["session_kwargs"]).start()  # type: ignore[arg-type]
        _WORKER["session"] = session
        atexit.register(session.close)
    return session  # type: ignore[return-value]


def _product_target_worker(
    target: SubcategoryTarget,
    max_products: int,
    retries: int,
    settle_ms: int,
) -> list[ProductRecord]:
    adapter: SiteAdapter = _WORKER["adapter"]  # type: ignore[assignment]
    session = _worker_session()
    return collect_products(
        adapter,
        category=target.category,
        subcategory=target.subcategory,
        query=target.search_query(),
        session=session,
        max_products=max_products,
        retries=retries,
        settle_ms=settle_ms,
    )


def _review_product_worker(
    product: ProductRecord,
    max_reviews: int,
    retries: int,
    settle_ms: int,
    page_delay_seconds: float,
) -> tuple[list[dict[str, object]], str, str]:
    adapter: SiteAdapter = _WORKER["adapter"]  # type: ignore[assignment]
    session = _worker_session()
    return scrape_product_reviews(
        adapter,
        product,
        session=session,
        max_reviews=max_reviews,
        retries=retries,
        settle_ms=settle_ms,
        page_delay_seconds=page_delay_seconds,
    )


def build_session_kwargs(
    adapter: SiteAdapter,
    block_resources: bool,
    cookies: list[dict] | None = None,
) -> dict[str, object]:
    """Build BrowserSession kwargs, honoring an adapter's blocking preference."""

    preference = getattr(adapter, "block_resources", None)
    effective = preference if preference is not None else block_resources
    return {
        "block_resources": effective,
        "prime_url": adapter.home_url or None,
        "locale": adapter.locale,
        "user_agent": adapter.user_agent or None,
        "extra_headers": adapter.extra_headers(),
        "cookies": cookies,
        "proxy": resolve_proxy_from_env(),
    }


# Backwards-compatible alias.
_session_kwargs = build_session_kwargs


# --------------------------------------------------------------------------- #
# Product batch
# --------------------------------------------------------------------------- #
def run_product_batch(
    adapter: SiteAdapter,
    *,
    output_dir: Path,
    targets: list[SubcategoryTarget] | None = None,
    max_products: int = 100,
    concurrency: int = 4,
    retries: int = 2,
    settle_ms: int = 350,
    block_resources: bool = True,
    cookies: list[dict] | None = None,
    logger: Logger = default_logger,
) -> list[dict[str, object]]:
    """Scrape every target's listing, write one CSV each, plus reports + zip."""

    targets = targets or list(adapter.default_targets)
    output_dir.mkdir(parents=True, exist_ok=True)
    start = _utc_now()
    results: dict[str, dict[str, object]] = {}

    def _record_result(target: SubcategoryTarget, records: list[ProductRecord], error: str) -> None:
        csv_path = output_dir / f"{slugify(target.category + '__' + target.subcategory)}.csv"
        _write_rows(csv_path, PRODUCT_CSV_FIELDS, [asdict(r) for r in records])
        if error:
            status = "failed"
        elif records:
            status = "success"
        else:
            status = "empty"
        key = f"{target.category}/{target.subcategory}"
        results[key] = {
            "category": target.category,
            "subcategory": target.subcategory,
            "csv": csv_path.name,
            "row_count": len(records),
            "status": status,
            "error": error,
        }
        elapsed = _format_elapsed((_utc_now() - start).total_seconds())
        logger(
            f"[elapsed {elapsed}] {status.upper()}: {target.category} / {target.subcategory} "
            f"rows={len(records)}"
        )

    concurrency = max(1, min(concurrency, len(targets)))
    session_kwargs = build_session_kwargs(adapter, block_resources, cookies)
    logger(
        f"Starting {adapter.label} product batch: targets={len(targets)} "
        f"max_products={max_products} concurrency={concurrency} "
        f"resource_blocking={'on' if block_resources else 'off'}"
    )

    if concurrency == 1:
        with BrowserSession(**session_kwargs) as session:  # type: ignore[arg-type]
            for target in targets:
                try:
                    records = collect_products(
                        adapter,
                        category=target.category,
                        subcategory=target.subcategory,
                        query=target.search_query(),
                        session=session,
                        max_products=max_products,
                        retries=retries,
                        settle_ms=settle_ms,
                    )
                    _record_result(target, records, "")
                except Exception as exc:  # noqa: BLE001
                    _record_result(target, [], str(exc))
    else:
        with ProcessPoolExecutor(
            max_workers=concurrency,
            initializer=_init_worker,
            initargs=(adapter, session_kwargs),
        ) as executor:
            future_map = {
                executor.submit(
                    _product_target_worker, target, max_products, retries, settle_ms
                ): target
                for target in targets
            }
            for future in as_completed(future_map):
                target = future_map[future]
                try:
                    records = future.result()
                    _record_result(target, records, "")
                except Exception as exc:  # noqa: BLE001
                    _record_result(target, [], str(exc))

    ordered = [
        results[f"{t.category}/{t.subcategory}"]
        for t in targets
        if f"{t.category}/{t.subcategory}" in results
    ]
    _write_product_reports(adapter, output_dir, ordered, start)
    return ordered


def _write_product_reports(
    adapter: SiteAdapter,
    output_dir: Path,
    results: list[dict[str, object]],
    start: dt.datetime,
) -> Path:
    report = {
        "site": adapter.name,
        "generated_at": _utc_now().isoformat(),
        "summary": {
            "total_subcategories": len(results),
            "successful": sum(1 for r in results if r["status"] == "success"),
            "empty": sum(1 for r in results if r["status"] == "empty"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
            "total_rows": sum(int(r["row_count"]) for r in results),
        },
        "results": results,
    }
    (output_dir / "run_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        f"{adapter.label} product scrape run report",
        f"Generated at: {report['generated_at']}",
        f"Total subcategories: {report['summary']['total_subcategories']}",
        f"Successful: {report['summary']['successful']}",
        f"Empty: {report['summary']['empty']}",
        f"Failed: {report['summary']['failed']}",
        f"Total rows: {report['summary']['total_rows']}",
        "",
    ]
    for r in results:
        lines.append(
            f"{str(r['status']).upper()}: {r['category']} / {r['subcategory']} "
            f"rows={r['row_count']} csv={r['csv']} error={r['error']}"
        )
    (output_dir / "run_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    zip_path = output_dir / f"{adapter.name}_product_csvs.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for r in results:
            csv_path = output_dir / str(r["csv"])
            if csv_path.exists():
                archive.write(csv_path, arcname=csv_path.name)
        archive.write(output_dir / "run_report.json", arcname="run_report.json")
        archive.write(output_dir / "run_report.txt", arcname="run_report.txt")
    return zip_path


# --------------------------------------------------------------------------- #
# Review batch (resumable)
# --------------------------------------------------------------------------- #
def load_products_from_dir(product_dir: Path, default_site: str = "") -> list[ProductRecord]:
    """Load product rows from every product CSV in a directory."""

    required = {"product_url"}
    products: list[ProductRecord] = []
    for csv_path in sorted(product_dir.glob("*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                continue
            for row in reader:
                url = (row.get("product_url") or "").strip()
                if not url:
                    continue
                products.append(
                    ProductRecord(
                        site=(row.get("site") or default_site).strip(),
                        category=(row.get("category") or "").strip(),
                        subcategory=(row.get("subcategory") or "").strip(),
                        title=(row.get("title") or "").strip(),
                        price=(row.get("price") or "").strip(),
                        rating=(row.get("rating") or "").strip(),
                        ratings_count=(row.get("ratings_count") or "").strip(),
                        reviews_count=(row.get("reviews_count") or "").strip(),
                        product_url=url,
                        product_id=(row.get("product_id") or "").strip(),
                        source_url=(row.get("source_url") or "").strip(),
                    )
                )
    return products


def _product_key(product: ProductRecord) -> str:
    return product.product_id or product.product_url


def _load_completed_keys(output_dir: Path) -> set[str]:
    status_path = output_dir / "product_review_status.csv"
    if not status_path.exists():
        return set()
    keys: set[str] = set()
    with status_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("status") or "").strip().lower() not in STATUS_TERMINAL_STATES:
                continue
            key = (row.get("product_id") or "").strip() or (row.get("product_url") or "").strip()
            if key:
                keys.add(key)
    return keys


def _review_rows_for_product(
    adapter: SiteAdapter,
    product: ProductRecord,
    raw_reviews: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in raw_reviews:
        rows.append(
            {
                "site": product.site or adapter.name,
                "category": product.category,
                "subcategory": product.subcategory,
                "product_title": product.title,
                "product_price": product.price,
                "product_listing_rating": product.rating,
                "product_ratings_count": product.ratings_count,
                "product_reviews_count": product.reviews_count,
                "product_url": product.product_url,
                "product_id": product.product_id,
                "source_url": product.source_url,
                "review_rating": str(raw.get("rating", "")),
                "review_title": str(raw.get("title", "")),
                "review_body": str(raw.get("body", "")),
                "reviewer": str(raw.get("reviewer", "")),
                "review_date": str(raw.get("date", "")),
                "helpful_count": str(raw.get("helpful_count", "")),
                "variant": str(raw.get("variant", "")),
                "city": str(raw.get("city", "")),
                "reviewer_badge": str(raw.get("reviewer_badge", "")),
            }
        )
    return rows


def _status_row(adapter: SiteAdapter, product: ProductRecord, status: str, count: int, error: str) -> dict[str, object]:
    return {
        "site": product.site or adapter.name,
        "category": product.category,
        "subcategory": product.subcategory,
        "product_title": product.title,
        "product_url": product.product_url,
        "product_id": product.product_id,
        "status": status,
        "review_count": count,
        "error": error,
    }


def _persist_product(
    adapter: SiteAdapter,
    output_dir: Path,
    product: ProductRecord,
    review_rows: list[dict[str, object]],
    status: str,
    count: int,
    error: str,
) -> None:
    if review_rows:
        sub_csv = output_dir / f"{slugify(product.category + '__' + product.subcategory)}-reviews.csv"
        _append_rows(sub_csv, REVIEW_CSV_FIELDS, review_rows)
        _append_rows(output_dir / "combined_reviews.csv", REVIEW_CSV_FIELDS, review_rows)

    status_row = _status_row(adapter, product, status, count, error)
    _append_rows(output_dir / "product_review_status.csv", PRODUCT_STATUS_FIELDS, [status_row])
    if status == "empty":
        _append_rows(output_dir / "empty_products.csv", PRODUCT_STATUS_FIELDS, [status_row])
    elif status == "failed":
        _append_rows(output_dir / "failed_products.csv", PRODUCT_STATUS_FIELDS, [status_row])


def run_review_batch(
    adapter: SiteAdapter,
    *,
    product_dir: Path,
    output_dir: Path,
    max_reviews: int = 100,
    concurrency: int = 8,
    retries: int = 2,
    settle_ms: int = 350,
    page_delay_seconds: float = 0.0,
    resume: bool = True,
    block_resources: bool = True,
    cookies: list[dict] | None = None,
    logger: Logger = default_logger,
) -> dict[str, object]:
    """Scrape reviews for every product CSV in ``product_dir`` (resumable)."""

    if not adapter.supports_reviews:
        raise RuntimeError(f"{adapter.label} does not support review scraping.")

    start = _utc_now()
    output_dir.mkdir(parents=True, exist_ok=True)
    products = load_products_from_dir(product_dir, default_site=adapter.name)
    completed = _load_completed_keys(output_dir) if resume else set()
    pending = [p for p in products if _product_key(p) not in completed]

    total = len(products)
    counts = {"success": 0, "empty": 0, "failed": 0, "reviews": 0}

    logger(
        f"Starting {adapter.label} review batch: total={total} "
        f"already_done={len(completed)} pending={len(pending)} "
        f"max_reviews={'uncapped' if max_reviews <= 0 else max_reviews} "
        f"concurrency={max(1, min(concurrency, max(1, len(pending))))} resume={'on' if resume else 'off'}"
    )

    if not pending:
        logger("No pending products. Resume state already complete.")
        return _write_review_reports(adapter, output_dir, total, len(completed), counts, start)

    concurrency = max(1, min(concurrency, len(pending)))
    session_kwargs = build_session_kwargs(adapter, block_resources, cookies)
    done = len(completed)

    def _handle(product: ProductRecord, raw: list[dict[str, object]], status: str, error: str) -> None:
        nonlocal done
        rows = _review_rows_for_product(adapter, product, raw)
        _persist_product(adapter, output_dir, product, rows, status, len(rows), error)
        counts[status] = counts.get(status, 0) + 1
        counts["reviews"] += len(rows)
        done += 1
        elapsed = _format_elapsed((_utc_now() - start).total_seconds())
        logger(
            f"[elapsed {elapsed}] {done}/{total} {status.upper()} "
            f"reviews={len(rows)} remaining={total - done} "
            f"{product.category}/{product.subcategory} :: {product.title[:60]}"
        )

    try:
        if concurrency == 1:
            with BrowserSession(**session_kwargs) as session:  # type: ignore[arg-type]
                for product in pending:
                    raw, status, error = scrape_product_reviews(
                        adapter,
                        product,
                        session=session,
                        max_reviews=max_reviews,
                        retries=retries,
                        settle_ms=settle_ms,
                        page_delay_seconds=page_delay_seconds,
                    )
                    _handle(product, raw, status, error)
        else:
            with ProcessPoolExecutor(
                max_workers=concurrency,
                initializer=_init_worker,
                initargs=(adapter, session_kwargs),
            ) as executor:
                future_map = {
                    executor.submit(
                        _review_product_worker,
                        product,
                        max_reviews,
                        retries,
                        settle_ms,
                        page_delay_seconds,
                    ): product
                    for product in pending
                }
                for future in as_completed(future_map):
                    product = future_map[future]
                    try:
                        raw, status, error = future.result()
                    except Exception as exc:  # noqa: BLE001
                        raw, status, error = [], "failed", str(exc)
                    _handle(product, raw, status, error)
    except KeyboardInterrupt:
        logger("Interrupted. Progress written to disk; rerun the same command to resume.")
        raise

    return _write_review_reports(adapter, output_dir, total, len(completed), counts, start)


def _write_review_reports(
    adapter: SiteAdapter,
    output_dir: Path,
    total: int,
    already_done: int,
    counts: dict[str, int],
    start: dt.datetime,
) -> dict[str, object]:
    report = {
        "site": adapter.name,
        "generated_at": _utc_now().isoformat(),
        "summary": {
            "products_total": total,
            "products_already_done_on_resume": already_done,
            "products_successful_this_run": counts.get("success", 0),
            "products_empty_this_run": counts.get("empty", 0),
            "products_failed_this_run": counts.get("failed", 0),
            "reviews_collected_this_run": counts.get("reviews", 0),
        },
    }
    (output_dir / "review_run_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        f"{adapter.label} review scrape run report",
        f"Generated at: {report['generated_at']}",
        f"Products total: {total}",
        f"Already done on resume: {already_done}",
        f"Successful this run: {counts.get('success', 0)}",
        f"Empty this run: {counts.get('empty', 0)}",
        f"Failed this run: {counts.get('failed', 0)}",
        f"Reviews collected this run: {counts.get('reviews', 0)}",
    ]
    (output_dir / "review_run_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    zip_path = output_dir / f"{adapter.name}_review_csvs.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for csv_path in sorted(output_dir.glob("*.csv")):
            archive.write(csv_path, arcname=csv_path.name)
        for name in ("review_run_report.json", "review_run_report.txt"):
            artifact = output_dir / name
            if artifact.exists():
                archive.write(artifact, arcname=name)
    report["zip"] = zip_path.name
    return report
