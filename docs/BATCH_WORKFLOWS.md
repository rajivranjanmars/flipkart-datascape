# Batch Workflows

This document explains the two batch scrapers and how they fit together.

## Overview

There are two batch stages:

1. product discovery
2. review enrichment

The normal flow is:

```text
batch_product_scraper -> product CSVs -> batch_review_scraper -> review CSVs and reports
```

## 1. Product discovery

Use the product batch scraper to collect product listings for the configured subcategories.

```bash
python -m scraper.batch_product_scraper \
  --output-dir data/runs/20260522_products \
  --max-products 100 \
  --concurrency 4 \
  --retries 2
```

### What it reads

The scraper uses the fixed subcategory list defined in `scraper.batch_product_scraper.SUBCATEGORY_TARGETS`.

### What it writes

The output directory contains:
- one CSV per subcategory
- `run_report.json`
- `run_report.txt`
- `flipkart_product_csvs.zip`

### When to use it

Use this step when you want a repeatable product catalog snapshot before scraping reviews.

## 2. Review enrichment

Use the review batch scraper to read the product CSVs and collect product-level reviews.

```bash
python -m scraper.batch_review_scraper \
  --product-dir data/runs/20260522_products \
  --output-dir data/runs/20260522_reviews \
  --max-reviews 100 \
  --concurrency 4 \
  --retries 2
```

### Uncapped and resumable mode

For long-running collection jobs:

```bash
python -m scraper.batch_review_scraper \
  --product-dir data/runs/20260522_products \
  --output-dir data/runs/20260522_reviews \
  --max-reviews 0 \
  --concurrency 1 \
  --retries 3 \
  --wait-seconds 8 \
  --empty-retry-wait-seconds 12 \
  --page-delay-seconds 2 \
  --product-delay-seconds 5
```

Important behavior:
- `--max-reviews 0` means no per-product review cap
- progress is written incrementally as each product completes
- `product_review_status.csv` is used as the resume ledger
- rerunning the same command continues from already-completed products
- log lines include UTC timestamps and elapsed runtime

## Main output files

### Product stage

- `*-<subcategory>.csv`: product listing rows
- `run_report.json`: structured run summary
- `run_report.txt`: plain-text run summary
- `flipkart_product_csvs.zip`: packaged CSV and reports

### Review stage

- `combined_reviews.csv`: all review rows in one file
- `*-reviews.csv`: one review CSV per subcategory
- `product_review_status.csv`: completion ledger for resume
- `empty_products.csv`: products with no parsed reviews
- `failed_products.csv`: products that failed during scraping
- `review_run_report.json`: structured review run summary
- `review_run_report.txt`: plain-text review run summary
- `scrape_config.json`: persisted runtime configuration
- `flipkart_review_csvs.zip`: packaged outputs

## Restarting an interrupted review run

If a review run stops, rerun the same command with the same `--output-dir`.

Example:

```bash
python -m scraper.batch_review_scraper \
  --product-dir data/runs/20260522_products \
  --output-dir data/runs/20260522_reviews \
  --max-reviews 0 \
  --concurrency 1 \
  --retries 3 \
  --wait-seconds 8 \
  --empty-retry-wait-seconds 12 \
  --page-delay-seconds 2 \
  --product-delay-seconds 5
```

If you intentionally want to ignore previous progress and start fresh, add:

```bash
--no-resume
```

## Legacy single-run entrypoint

`main.py` remains available for a simpler one-URL workflow.

```bash
python main.py "https://www.flipkart.com/search?q=smartphones" --max-products 20 --output-dir data
```

Use it when you want a quick CSV from one listing URL instead of the full batch pipeline.
