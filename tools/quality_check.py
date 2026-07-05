#!/usr/bin/env python3
"""Read-only data-quality reporter for a scrape run directory.

Usage:
    python tools/quality_check.py data/runs/bg_<TS>
    python tools/quality_check.py data/runs/bg_<TS>/amazon_reviews

Walks the directory, classifies each CSV by its header, and reports counts +
field-population rates + failure/empty tallies + a few sample rows. Used to judge
"is the data we're collecting actually good?" during background-run polling.

Pure stdlib; never writes anything.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# Header signatures (subset that must be present).
PRODUCT_KEYS = {"product_url", "title", "price"}
REVIEW_KEYS = {"product_url", "review_body", "review_rating"}
STATUS_KEYS = {"status", "product_url"}

# Files we treat specially so review rows aren't double-counted.
COMBINED_REVIEWS = "combined_reviews.csv"
STATUS_FILE = "product_review_status.csv"
FAILED_FILE = "failed_products.csv"
EMPTY_FILE = "empty_products.csv"


def _read_rows(path: Path) -> tuple[list[str], list[dict]]:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            fields = reader.fieldnames or []
            return list(fields), list(reader)
    except Exception as exc:  # noqa: BLE001
        print(f"    ! could not read {path.name}: {exc}")
        return [], []


def _pct(part: int, whole: int) -> str:
    if whole == 0:
        return "n/a"
    return f"{100.0 * part / whole:.0f}%"


def _nonempty(rows: list[dict], key: str) -> int:
    return sum(1 for r in rows if str(r.get(key, "")).strip())


def _classify(path: Path, fields: list[str]) -> str:
    fieldset = set(fields)
    name = path.name
    if name == COMBINED_REVIEWS:
        return "reviews_combined"
    if name == STATUS_FILE:
        return "status"
    if name in (FAILED_FILE, EMPTY_FILE):
        return "status_subset"
    if REVIEW_KEYS.issubset(fieldset):
        return "reviews_other"  # per-subcategory review files (skip to avoid dupes)
    if PRODUCT_KEYS.issubset(fieldset):
        return "products"
    return "unknown"


def _report_products(path: Path, rows: list[dict]) -> None:
    n = len(rows)
    title_ok = _nonempty(rows, "title")
    price_ok = _nonempty(rows, "price")
    rating_ok = _nonempty(rows, "rating")
    print(f"  [products] {path.name}: {n} rows | title {_pct(title_ok, n)} | "
          f"price {_pct(price_ok, n)} | rating {_pct(rating_ok, n)}")
    for r in rows[:2]:
        print(f"      - {str(r.get('title',''))[:48]!r} | {r.get('price','')} | "
              f"rt={r.get('rating','')} | id={r.get('product_id','')}")


def _report_reviews(path: Path, rows: list[dict]) -> None:
    n = len(rows)
    rating_ok = _nonempty(rows, "review_rating")
    body_ok = _nonempty(rows, "review_body")
    reviewer_ok = _nonempty(rows, "reviewer")
    products = len({r.get("product_url", "") for r in rows})
    print(f"  [reviews] {path.name}: {n} reviews across {products} products | "
          f"rating {_pct(rating_ok, n)} | body {_pct(body_ok, n)} | "
          f"reviewer {_pct(reviewer_ok, n)}")
    for r in rows[:3]:
        print(f"      - {r.get('review_rating','')}★ "
              f"{str(r.get('review_title',''))[:30]!r} by "
              f"{str(r.get('reviewer',''))[:18]!r} :: {str(r.get('review_body',''))[:45]}")


def _report_status(path: Path, rows: list[dict]) -> None:
    by_status: dict[str, int] = defaultdict(int)
    for r in rows:
        by_status[str(r.get("status", "")).strip() or "?"] += 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
    print(f"  [status] {path.name}: {len(rows)} products | {summary}")
    # Surface a couple of distinct error messages (auth wall / blocks / etc.).
    errors = []
    seen = set()
    for r in rows:
        err = str(r.get("error", "")).strip()
        if err and err not in seen:
            seen.add(err)
            errors.append(err)
        if len(errors) >= 3:
            break
    for err in errors:
        print(f"      ! {err[:90]}")


def _report_run_json(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    summary = data.get("summary")
    if summary:
        print(f"  [report] {path.name}: {json.dumps(summary)}")


def summarize(root: Path) -> None:
    csv_paths = sorted(root.rglob("*.csv"))
    json_reports = sorted(root.rglob("run_report.json")) + sorted(root.rglob("review_run_report.json"))

    if not csv_paths and not json_reports:
        print(f"(no CSVs yet under {root})")
        return

    by_dir: dict[Path, list[Path]] = defaultdict(list)
    for p in csv_paths:
        by_dir[p.parent].append(p)

    for d in sorted(by_dir):
        rel = d.relative_to(root) if d != root else Path(".")
        print(f"\n=== {rel} ===")
        for p in sorted(by_dir[d]):
            fields, rows = _read_rows(p)
            kind = _classify(p, fields)
            if kind == "products":
                _report_products(p, rows)
            elif kind == "reviews_combined":
                _report_reviews(p, rows)
            elif kind == "status":
                _report_status(p, rows)
            elif kind in ("reviews_other", "status_subset", "unknown"):
                # Skip noisy/duplicate files but note failures explicitly.
                if p.name == FAILED_FILE and rows:
                    print(f"  [FAILED] {p.name}: {len(rows)} products")
                    _report_status(p, rows)

    for jr in json_reports:
        _report_run_json(jr)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python tools/quality_check.py <run_dir>")
        return 2
    root = Path(argv[1])
    if not root.exists():
        print(f"not found: {root}")
        return 2
    print(f"Quality check: {root}")
    summarize(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
