# Batch Workflows

How the batch stages fit together, for any supported site (`flipkart`, `amazon`,
`myntra`, `meesho`). Everything below is available both in the interactive app
(`python -m scraper`) and as flag-based commands (shown here).

## Overview

```text
products  ->  product CSVs  ->  reviews  ->  review CSVs + reports
```

`pipeline` runs both stages back-to-back into one output directory.

> Reviews are only supported on review-capable sites (Flipkart, Amazon). Myntra
> and Meesho are product-listing only.

## 1. Product discovery

Collect listings for a site's preset categories:

```bash
python -m scraper products \
  --site flipkart \
  --output-dir data/runs/fk_products \
  --max-products 100 \
  --concurrency 4 \
  --profile balanced
```

The preset category list lives in each adapter's `default_targets`
(e.g. `scraper.sites.flipkart.FlipkartAdapter.default_targets`).

For a single ad-hoc query or a full listing URL instead of the presets:

```bash
python -m scraper search "smartphones" --site flipkart --output-dir data/runs/fk_search --max-products 50
python -m scraper search "https://www.flipkart.com/search?q=laptops" --site flipkart --output-dir data/runs/fk_url
```

### Product output

- `<category>-<subcategory>.csv` — one per preset category
- `<site>-search-<query>.csv` — for `search` mode
- `run_report.json` / `run_report.txt`
- `<site>_product_csvs.zip`

## 2. Review enrichment (resumable)

Read product CSVs and collect reviews:

```bash
python -m scraper reviews \
  --site flipkart \
  --product-dir data/runs/fk_products \
  --output-dir data/runs/fk_reviews \
  --max-reviews 100 \
  --concurrency 8 \
  --profile balanced
```

### Uncapped, gentle, long-running

```bash
python -m scraper reviews \
  --site flipkart \
  --product-dir data/runs/fk_products \
  --output-dir data/runs/fk_reviews \
  --max-reviews 0 \
  --concurrency 2 \
  --profile polite
```

Behavior:
- `--max-reviews 0` = no per-product cap
- progress is written to disk as each product completes
- `product_review_status.csv` is the resume ledger
- **rerun the same command to resume**; add `--no-resume` to start fresh
- log lines include UTC timestamps and elapsed runtime

### Review output

- `combined_reviews.csv` — all reviews in one file
- `<category>-<subcategory>-reviews.csv` — per category
- `product_review_status.csv` — resume ledger
- `empty_products.csv` / `failed_products.csv`
- `review_run_report.json` / `.txt`
- `<site>_review_csvs.zip`

## 3. Full pipeline

Products then reviews, into `<output-dir>/products` and `<output-dir>/reviews`:

```bash
python -m scraper pipeline \
  --site flipkart \
  --output-dir data/runs/fk_all \
  --max-products 50 \
  --max-reviews 50 \
  --profile fast
```

## Speed profiles

`--profile fast|balanced|polite` trades speed for politeness (resource blocking,
wait times, and default concurrency). See the README table. Use `--concurrency 0`
to accept the profile's default.

## Restarting an interrupted run

Rerun the exact same `reviews` (or `pipeline`) command with the same
`--output-dir`. Completed products are skipped via the resume ledger.
