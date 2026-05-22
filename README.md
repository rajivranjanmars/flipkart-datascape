# Flipkart Datascape

A Python toolkit for collecting Flipkart product listings and review data in structured CSV, JSON, and ZIP outputs.

This repository includes:
- a simple single-URL review scraper for one category or listing page
- a batch product scraper for a fixed set of categories and subcategories
- a resumable batch review scraper that can continue long-running jobs without starting over

The project is designed for practical data collection workflows: scrape product listings first, then enrich those products with review data.

## What it does

`Flipkart Datascape` supports three main workflows.

1. `main.py`  
   Scrape reviews from a single Flipkart category or listing URL and save them incrementally.

2. `scraper.batch_product_scraper`  
   Scrape up to a fixed number of products for each configured subcategory and write one CSV per subcategory, plus run reports and a ZIP archive.

3. `scraper.batch_review_scraper`  
   Read the product CSVs from the batch product scraper, visit each product review page, and write review CSVs with resumable checkpointing.

## Repository layout

```text
.
├── README.md
├── CONTRIBUTING.md
├── docs/
│   └── BATCH_WORKFLOWS.md
├── main.py
├── requirements.txt
├── data/
│   └── .gitkeep
├── scraper/
│   ├── batch_product_scraper.py
│   ├── batch_review_scraper.py
│   ├── product_list.py
│   ├── review_scraper.py
│   └── utils.py
└── tests/
    ├── test_batch_product_scraper.py
    └── test_batch_review_scraper.py
```

## Requirements

- Python 3.11+
- pip
- Playwright browser dependencies

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install the Playwright browser used by the scraper:

```bash
python -m playwright install
```

If Playwright is already set up on your machine, you only need to do this once.

## Quick start

### Option 1: Scrape reviews from one category or listing URL

Use `main.py` if you want a simple, direct entrypoint.

```bash
python main.py "https://www.flipkart.com/search?q=smartphones" --max-products 20 --output-dir data
```

What this does:
- collects up to `20` product URLs from the listing
- scrapes reviews for each product
- writes a timestamped CSV such as `data/reviews_20260522_120000.csv`

### Option 2: Scrape products for all configured subcategories

```bash
python -m scraper.batch_product_scraper \
  --output-dir data/runs/20260522_products \
  --max-products 100 \
  --concurrency 4 \
  --retries 2
```

This writes:
- one CSV per subcategory
- `run_report.json`
- `run_report.txt`
- `flipkart_product_csvs.zip`

### Option 3: Scrape reviews for the batch product output

```bash
python -m scraper.batch_review_scraper \
  --product-dir data/runs/20260522_products \
  --output-dir data/runs/20260522_reviews \
  --max-reviews 100 \
  --concurrency 4 \
  --retries 2
```

For very large collection jobs, use conservative settings and resumable output:

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

In this mode:
- `--max-reviews 0` means uncapped review scraping per product
- completed products are written to disk immediately
- rerunning the same command resumes from `product_review_status.csv`
- progress logs include timestamps and elapsed runtime

## Configured batch coverage

The batch product scraper is configured for 18 subcategories across:
- Beauty & Care
- Clothing
- Electronics
- Footwear
- Wearable Devices

The exact target list lives in `scraper.batch_product_scraper.SUBCATEGORY_TARGETS`.

## Output files

### Product batch output

A product run directory contains files like:

```text
beauty-care-bath-body.csv
beauty-care-fragrances.csv
...
run_report.json
run_report.txt
flipkart_product_csvs.zip
```

Each product CSV contains:
- `category`
- `subcategory`
- `title`
- `price`
- `rating`
- `ratings_count`
- `reviews_count`
- `product_url`
- `product_id`
- `source_url`

### Review batch output

A review run directory contains files like:

```text
combined_reviews.csv
beauty-care-bath-body-reviews.csv
...
product_review_status.csv
empty_products.csv
failed_products.csv
review_run_report.json
review_run_report.txt
scrape_config.json
flipkart_review_csvs.zip
```

`product_review_status.csv` is the key resume ledger. If a long-running job stops, rerun the same command against the same `--output-dir`.

## Documentation

- [Batch Workflows](docs/BATCH_WORKFLOWS.md)
- [Contributing](CONTRIBUTING.md)

## Typical usage pattern

For most users, the recommended sequence is:

1. Run the product batch scraper.
2. Inspect the generated product CSVs.
3. Run the review batch scraper using that product directory.
4. Resume the review scraper with the same command if the run is interrupted.

## Testing

Run the current test suite with:

```bash
python -m unittest tests.test_batch_product_scraper tests.test_batch_review_scraper
```

You can also compile-check the scraper modules:

```bash
python -m py_compile scraper/batch_product_scraper.py scraper/batch_review_scraper.py
```

## Notes on generated data

Generated scrape outputs and logs are intentionally excluded from git tracking. The repository keeps the code and docs public-facing, while run artifacts stay local.

## Limitations

- Flipkart page structure may change over time.
- Large uncapped review runs can take a long time.
- Network throttling and empty responses can reduce completeness.
- This project does not guarantee stable extraction for every category or product page layout.

## Responsible use

Before scraping any website at scale, review the site's terms, robots guidance, and applicable local rules. Use conservative request patterns and avoid disruptive traffic.
